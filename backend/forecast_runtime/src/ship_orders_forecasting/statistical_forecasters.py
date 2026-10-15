"""Sklearn-compatible, past-only statistical forecasting candidates.

Train row dates index the same direct-target series as the other regressors.
A forecast advances from the last Train row to the requested row (four months
under C-1 label availability and C+3 targets). Future exogenous paths contain
only known feature values; held-out target values are never passed to fit.
"""
from functools import lru_cache
import warnings

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.decomposition import PCA
from sklearn.linear_model import TweedieRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.utils.validation import check_array, check_X_y, check_is_fitted

STATISTICAL_MODELS = (
    'ARIMAX', 'SARIMAX', 'VAR', 'VARX', 'VECM',
    'Markov Switching AR', 'State Space / Kalman Filter',
)


def attach_forecast_context(X, grid, horizon, origin):
    """Attach only the known X path between the last Train date and this origin."""
    output = X.copy()
    if not isinstance(X.index, pd.DatetimeIndex):
        return output
    first = X.index[-1].to_period('M') + 1
    last = pd.Timestamp(origin).to_period('M')
    steps = last.ordinal - X.index[-1].to_period('M').ordinal
    if steps <= 0:
        raise ValueError('Forecast origin must follow the last Train row.')
    monthly = grid.xs(horizon, level='선행개월')
    monthly.index = monthly.index.to_period('M')
    periods = pd.period_range(first, last, freq='M')
    # No actual/label column is included in this metadata.
    path = monthly.reindex(periods)[list(X.columns)].to_numpy(dtype=float)
    output.attrs['forecast_steps'] = steps
    output.attrs['known_future_exog'] = path
    return output


def _finite_prediction(values):
    result = np.asarray(values, dtype=float)
    if not np.isfinite(result).all():
        raise ValueError('Statistical forecast produced nonfinite values.')
    return result


def _regularized_vecm(system, order, rank, ridge):
    """Train-only reduced-rank error correction when ML covariance is singular."""
    changes = np.diff(system, axis=0)
    response, levels = changes[order:], system[order:-1]
    short = np.column_stack([
        *[changes[order-lag:-lag] for lag in range(1, order+1)],
        np.ones(len(response))])
    residual0 = response - short @ np.linalg.lstsq(short, response, rcond=None)[0]
    residual1 = levels - short @ np.linalg.lstsq(short, levels, rcond=None)[0]
    n, k = response.shape
    s00, s11 = residual0.T @ residual0/n, residual1.T @ residual1/n
    s01 = residual0.T @ residual1/n
    # Fixed numerical regularization uses only Train covariance. It is not
    # adjusted using Validation/Test errors or observations.
    r00 = s00 + np.eye(k)*max(float(ridge)*float(np.trace(s00))/k, 1e-10)
    r11 = s11 + np.eye(k)*max(float(ridge)*float(np.trace(s11))/k, 1e-10)
    eigenvalues, eigenvectors = np.linalg.eigh(r11)
    whitening = (eigenvectors / np.sqrt(eigenvalues)) @ eigenvectors.T
    canonical = whitening @ s01.T @ np.linalg.solve(r00, s01) @ whitening
    _, vectors = np.linalg.eigh((canonical+canonical.T)/2)
    if rank:
        beta = whitening @ vectors[:, -rank:]
        alpha = s01 @ beta @ np.linalg.inv(beta.T @ r11 @ beta)
        pi = alpha @ beta.T
    else:
        pi = np.zeros((k, k))
    short_coef = np.linalg.lstsq(short, response-levels @ pi.T, rcond=None)[0]
    return pi, short_coef


@lru_cache(maxsize=256)
def _fit_markov(target_bytes, n, regimes, maxiter):
    from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression
    target = np.frombuffer(target_bytes, dtype=np.float64, count=n).copy()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        model = MarkovAutoregression(target, k_regimes=regimes, order=1,
                                    trend='c', switching_ar=True, switching_variance=True)
        result = model.fit(disp=False, maxiter=maxiter, em_iter=5, search_reps=0)
    if not np.isfinite(result.params).all():
        raise ValueError('Markov Switching AR estimation failed.')
    params = result.params
    state = {
        'means': np.array([params[model.parameters[r, 'exog']][0] for r in range(regimes)]),
        'phi': np.array([params[model.parameters[r, 'autoregressive']][0] for r in range(regimes)]),
        'transition': np.asarray(model.regime_transition_matrix(params))[:, :, 0],
        'probabilities': np.asarray(result.filtered_marginal_probabilities)[-1].copy(),
        'converged': bool(result.mle_retvals.get('converged', False)),
    }
    return state, tuple(str(w.message) for w in caught)


class StatisticalForecastRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, kind='ARIMAX', ar_order=1, difference=0, seasonal_ar=1,
                 seasonal_period=12, max_factors=3, forecast_steps=4,
                 maxiter=60, ridge_alpha=1e-4, coint_rank=1, n_regimes=2):
        self.kind = kind
        self.ar_order = ar_order
        self.difference = difference
        self.seasonal_ar = seasonal_ar
        self.seasonal_period = seasonal_period
        self.max_factors = max_factors
        self.forecast_steps = forecast_steps
        self.maxiter = maxiter
        self.ridge_alpha = ridge_alpha
        self.coint_rank = coint_rank
        self.n_regimes = n_regimes

    def fit(self, X, y):
        if self.kind not in STATISTICAL_MODELS:
            raise ValueError(f'Unknown statistical candidate: {self.kind}')
        values, target = check_X_y(X, y, dtype=float, y_numeric=True)
        if len(target) < 12 or self.ar_order not in {1, 2} or self.difference not in {0, 1}:
            raise ValueError('Statistical models need chronological history and valid orders.')
        if self.max_factors < 1 or self.forecast_steps < 1 or self.maxiter < 1:
            raise ValueError('Factors, forecast horizon and iteration limit must be positive.')
        self.n_features_in_ = values.shape[1]
        self.feature_names_in_ = np.asarray(getattr(X, 'columns', []), dtype=object)
        self.used_feature_names_ = ([] if self.kind == 'Markov Switching AR'
                                    else self.feature_names_in_.tolist())
        self.last_period_ = None
        if isinstance(getattr(X, 'index', None), (pd.DatetimeIndex, pd.PeriodIndex)):
            periods = pd.PeriodIndex(X.index, freq='M')
            if not periods.equals(pd.period_range(periods[0], periods[-1], freq='M')):
                raise ValueError('Statistical Train months must be unique and consecutive.')
            self.last_period_ = periods[-1]
        self.default_steps_ = int(getattr(X, 'attrs', {}).get('forecast_steps', self.forecast_steps))
        self.future_X_ = getattr(X, 'attrs', {}).get('known_future_exog')
        self.input_mask_ = np.ones(values.shape[1], dtype=bool)
        if self.kind == 'VARX' and self.future_X_ is not None:
            # Path availability is known at issue time. It selects no labels
            # and imputes no missing intermediate observations.
            self.input_mask_ = np.isfinite(np.asarray(self.future_X_)).all(axis=0)
            if not self.input_mask_.any():
                raise ValueError('VARX has no fully observed exogenous input path.')
            self.used_feature_names_ = self.feature_names_in_[self.input_mask_].tolist()
        used_values = values[:, self.input_mask_]
        self.x_scaler_ = StandardScaler().fit(used_values)
        self.y_scaler_ = StandardScaler().fit(target[:, None])
        scaled = self.x_scaler_.transform(used_values)
        rank = int(np.linalg.matrix_rank(scaled))
        self.pca_ = None
        if rank:
            components = min(int(self.max_factors), rank, len(values)-3)
            self.pca_ = PCA(n_components=components, svd_solver='full').fit(scaled)
            factors = self.pca_.transform(scaled)
        else:
            factors = np.empty((len(values), 0))
        self.factor_count_ = factors.shape[1]
        self.target_ = self.y_scaler_.transform(target[:, None]).ravel()
        self.fit_warnings_ = []
        self.forecast_cache_ = {}
        self.constant_ = float(target[0]) if np.ptp(target) <= 1e-12 else None
        if self.constant_ is not None:
            return self

        if self.kind in {'ARIMAX', 'SARIMAX', 'State Space / Kalman Filter'}:
            exog = factors if self.factor_count_ else None
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                if self.kind == 'State Space / Kalman Filter':
                    from statsmodels.tsa.statespace.structural import UnobservedComponents
                    model = UnobservedComponents(self.target_, level='local linear trend', exog=exog)
                else:
                    from statsmodels.tsa.statespace.sarimax import SARIMAX
                    seasonal = ((int(self.seasonal_ar), 0, 0, int(self.seasonal_period))
                                if self.kind == 'SARIMAX' else (0, 0, 0, 0))
                    model = SARIMAX(self.target_, exog=exog,
                        order=(int(self.ar_order), int(self.difference), 0),
                        seasonal_order=seasonal, trend='c',
                        enforce_stationarity=True, enforce_invertibility=True,
                        mle_regression=True)
                self.result_ = model.fit(disp=False, maxiter=int(self.maxiter))
            self.fit_warnings_ = [str(w.message) for w in caught]
            self.converged_ = bool(self.result_.mle_retvals.get('converged', False))
            if not np.isfinite(self.result_.params).all():
                raise ValueError(f'{self.kind} estimation failed.')
            names = self.result_.model.param_names
            if self.kind == 'State Space / Kalman Filter':
                self.beta_ = np.array([p for name, p in zip(names, self.result_.params)
                                       if name.startswith('beta.')])
            else:
                exog_names = self.result_.model.exog_names or []
                self.beta_ = np.array([self.result_.params[names.index(name)] for name in exog_names])
            if len(self.beta_) != self.factor_count_:
                raise ValueError('Exogenous coefficients could not be identified.')

        elif self.kind == 'Markov Switching AR':
            self.result_, messages = _fit_markov(
                self.target_.astype(np.float64).tobytes(), len(self.target_),
                int(self.n_regimes), int(self.maxiter))
            self.fit_warnings_ = list(messages)
            self.converged_ = self.result_['converged']

        elif self.kind == 'VECM':
            from statsmodels.tsa.vector_ar.vecm import VECM
            # Factors are estimated from Train only to keep small-sample systems identifiable.
            self.system_ = np.column_stack([self.target_, factors])
            if self.system_.shape[1] < 2:
                raise ValueError('VECM needs at least one nonconstant input factor.')
            rank = min(int(self.coint_rank), self.system_.shape[1]-1)
            try:
                self.result_ = VECM(self.system_, k_ar_diff=int(self.ar_order),
                                    coint_rank=rank, deterministic='co').fit()
                # An ill-conditioned covariance can return complex short-run
                # coefficients instead of raising during fit. statsmodels then
                # fails while adding gamma to its real-valued VAR matrices.
                # Use the same Train-only regularization as for a singular fit.
                if np.iscomplexobj(self.result_.gamma):
                    raise np.linalg.LinAlgError('VECM returned complex short-run coefficients.')
            except np.linalg.LinAlgError:
                self.vecm_pi_, self.vecm_short_ = _regularized_vecm(
                    self.system_, int(self.ar_order), rank, float(self.ridge_alpha))
                self.fit_warnings_.append(
                    'VECM Train covariance singular or coefficients complex: fixed Train-only ridge reduced-rank estimation.')
            else:
                if not np.isfinite(self.result_.alpha).all():
                    raise ValueError('VECM estimation failed.')
        else:
            if self.kind == 'VARX':
                endogenous_factors = 1 if self.factor_count_ >= 2 else 0
                self.system_ = np.column_stack([self.target_, factors[:, :endogenous_factors]])
                self.exog_ = factors[:, endogenous_factors:]
                self.endogenous_factor_count_ = endogenous_factors
            else:
                self.system_ = np.column_stack([self.target_, factors])
                self.exog_ = np.empty((len(values), 0))
                self.endogenous_factor_count_ = self.factor_count_
            order = int(self.ar_order)
            regressors = np.column_stack([np.ones(len(values)-order),
                *[self.system_[order-lag:-lag] for lag in range(1, order+1)],
                self.exog_[order:]])
            penalty = np.eye(regressors.shape[1]) * float(self.ridge_alpha)
            penalty[0, 0] = 0.
            self.coef_ = np.linalg.solve(
                regressors.T @ regressors + penalty, regressors.T @ self.system_[order:])
        if self.kind not in {'VAR', 'VARX'}:
            # Only the forecast profile and exogenous coefficients are needed
            # for PI/SHAP. Do not retain every likelihood matrix for thousands
            # of candidate/origin fits in the strategy grid.
            for length in range(1, max(self.default_steps_, self.forecast_steps)+1):
                self._state_forecast(length)
            if hasattr(self, 'result_'):
                del self.result_
        return self

    def _factors(self, X):
        scaled = self.x_scaler_.transform(np.asarray(X)[:, self.input_mask_])
        return self.pca_.transform(scaled) if self.pca_ is not None else np.empty((len(X), 0))

    def _steps(self, X):
        if self.last_period_ is not None and isinstance(getattr(X, 'index', None), (pd.DatetimeIndex, pd.PeriodIndex)):
            steps = pd.PeriodIndex(X.index, freq='M').asi8 - self.last_period_.ordinal
            if np.any(steps <= 0):
                raise ValueError('Statistical forecasts require dates after the last Train row.')
            return steps.astype(int)
        return np.full(len(X), self.default_steps_, dtype=int)

    def _state_forecast(self, steps):
        if steps not in self.forecast_cache_:
            if not hasattr(self, 'result_') and not hasattr(self, 'vecm_pi_'):
                raise ValueError('Requested date exceeds the configured forecast profile.')
            if self.kind == 'VECM':
                if hasattr(self, 'vecm_pi_'):
                    history = self.system_.tolist()
                    changes = np.diff(self.system_, axis=0).tolist()
                    for _ in range(int(steps)):
                        short = np.r_[*[changes[-lag] for lag in range(1, int(self.ar_order)+1)], 1.]
                        delta = self.vecm_pi_ @ history[-1] + short @ self.vecm_short_
                        history.append((np.asarray(history[-1])+delta).tolist())
                        changes.append(delta.tolist())
                    value = float(history[-1][0])
                else:
                    value = float(self.result_.predict(steps=int(steps))[-1, 0])
            elif self.kind == 'Markov Switching AR':
                means, phi, transition = (self.result_[key] for key in ['means', 'phi', 'transition'])
                probabilities = self.result_['probabilities'].copy()
                centered_moments = probabilities * (self.target_[-1] - means)
                for _ in range(int(steps)):
                    probabilities = transition @ probabilities
                    centered_moments = phi * (transition @ centered_moments)
                value = float(means @ probabilities + centered_moments.sum())
            else:
                kwargs = {'exog': np.zeros((int(steps), self.factor_count_))} if self.factor_count_ else {}
                # MLE regression enters the observation equation only. The zero-exog
                # forecast isolates latent errors/trend; add this sample's known
                # terminal exog separately. No unavailable intermediate X is invented.
                value = float(np.asarray(self.result_.get_forecast(steps=int(steps), **kwargs).predicted_mean)[-1])
            self.forecast_cache_[steps] = value
        return self.forecast_cache_[steps]

    def predict(self, X):
        check_is_fitted(self, 'y_scaler_')
        values = check_array(X, dtype=float)
        if values.shape[1] != self.n_features_in_:
            raise ValueError('Statistical forecast feature count differs from Train.')
        if hasattr(X, 'columns') and len(self.feature_names_in_) and list(X.columns) != self.feature_names_in_.tolist():
            raise ValueError('Statistical forecast feature order differs from Train.')
        if self.constant_ is not None:
            return np.full(len(values), self.constant_)
        steps = self._steps(X)
        factors = self._factors(values)
        predicted = []
        for i, length in enumerate(steps):
            if self.kind in {'VAR', 'VARX'}:
                history = self.system_.tolist()
                if self.kind == 'VARX' and self.exog_.shape[1]:
                    if self.future_X_ is None or len(self.future_X_) < length:
                        raise ValueError('VARX requires the known intermediate exogenous X path.')
                    path = np.asarray(self.future_X_[:length], dtype=float).copy()
                    path[-1] = values[i]
                    if not np.isfinite(path[:, self.input_mask_]).all():
                        raise ValueError('VARX known exogenous path contains missing input rows.')
                    exog_path = self._factors(path)[:, self.endogenous_factor_count_:]
                else:
                    exog_path = np.empty((int(length), 0))
                for j in range(int(length)):
                    design = np.r_[1., *[history[-lag] for lag in range(1, int(self.ar_order)+1)], exog_path[j]]
                    history.append((design @ self.coef_).tolist())
                value = history[-1][0]
            else:
                value = self._state_forecast(int(length))
                if self.kind in {'ARIMAX', 'SARIMAX', 'State Space / Kalman Filter'}:
                    value += float(factors[i] @ self.beta_)
            predicted.append(value)
        return _finite_prediction(self.y_scaler_.inverse_transform(np.asarray(predicted)[:, None]).ravel())


class ScaledTweedieRegressor(RegressorMixin, BaseEstimator):
    def __init__(self, power=1.5, alpha=1.0, max_iter=300):
        self.power = power
        self.alpha = alpha
        self.max_iter = max_iter

    def fit(self, X, y):
        values, target = check_X_y(X, y, dtype=float, y_numeric=True)
        if (target < 0).any() or not 1 < self.power < 2:
            raise ValueError('Compound Poisson-Gamma Tweedie requires y>=0 and 1<power<2.')
        self.n_features_in_ = values.shape[1]
        self.x_scaler_ = StandardScaler().fit(values)
        self.target_scale_ = max(float(target.mean()), 1.)
        self.constant_ = float(target[0]) if np.ptp(target) <= 1e-12 else None
        self.feature_names_in_ = np.asarray(getattr(X, 'columns', []), dtype=object)
        if self.constant_ is None:
            self.regressor_ = TweedieRegressor(power=self.power, alpha=self.alpha,
                link='log', max_iter=self.max_iter, tol=1e-6).fit(
                    self.x_scaler_.transform(values), target/self.target_scale_)
        return self

    def predict(self, X):
        check_is_fitted(self, 'x_scaler_')
        values = check_array(X, dtype=float)
        if values.shape[1] != self.n_features_in_:
            raise ValueError('Tweedie feature count differs from Train.')
        if self.constant_ is not None:
            return np.full(len(values), self.constant_)
        scaled = self.x_scaler_.transform(values)
        eta = scaled @ self.regressor_.coef_ + self.regressor_.intercept_
        # Fixed numerical guard; no Validation/Test-based clipping threshold.
        return np.exp(np.clip(eta, -30., 30.)) * self.target_scale_
