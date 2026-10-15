"""Matplotlib으로 직접 그리는 45도 회전 하삼각 상관관계 그림."""

from pathlib import Path
import argparse

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from matplotlib.ticker import FormatStrFormatter
import numpy as np
import pandas as pd


TITLE = "가스 운반선 변수 상관관계 히트맵 (45° 회전, 중복 제외)"
FILENAME = "가스_운반선_상관관계_45도_삼각형"
FEATURES = [
    "원유 평균 가격(USD/bbl)", "천연가스 가격지수(2010=100)",
    "일본 LNG 가격(USD/MMBtu)", "싱가포르_벙커유판매량_천톤",
    "글로벌_컨테이너처리량지수",
    "세계_실질상품수출_백만2010USD_계절조정",
    "세계_실질상품수입_백만2010USD_계절조정",
    "세계_산업생산_백만2010USD_계절조정",
    "글로벌_공급망압력지수(표준편차)",
    "GPR(세계지정학위험지수)", "GPRT(지정학위협지수)",
    "GPRA(지정학행동지수)",
    "미국TPU(EPUTRADE 무역정책불확실성지수)",
    "미국TPU(Caldara 무역정책불확실성지수)",
    "중국TPU(무역정책불확실성지수)", "수주용량_2개월전",
]


def draw_rotated_correlation(correlation, target="수주용량", title=TITLE,
                             output_stem=None, highlight_target=True,
                             target_label=None):
    """하삼각 i>j만 그린다. 전체 컬러 또는 종속변수 강조 모드를 지원한다.

    종속변수를 마지막에 배치하면 해당 행 전체가 오른쪽 사선 띠가 된다.
    숫자·라벨은 회전하지 않는다. NaN은 0으로 바꾸지 않고 '—'로 표시한다.
    강조 모드에서만 다른 변수 간 셀에 |r|의 회색 명암을 적용하고 검은 테두리를 그린다.
    """
    if not correlation.index.equals(correlation.columns) or not correlation.columns.is_unique:
        raise ValueError("상관행렬의 행·열 이름과 순서는 같고 중복이 없어야 합니다.")
    if target not in correlation.columns or len(correlation) < 2:
        raise ValueError("종속변수와 최소 한 개의 설명변수가 필요합니다.")
    names = [name for name in correlation.columns if name != target] + [target]
    # 계산에 쓰는 마스터 열 이름과 그래프에 표시할 processed 원본 열 이름을 분리한다.
    # 다른 설명변수는 실제 열 이름 그대로 표시한다.
    display_names = [target_label if name == target and target_label is not None else name
                     for name in names]
    values = correlation.loc[names, names].to_numpy(dtype=float)
    if not np.allclose(values, values.T, equal_nan=True):
        raise ValueError("상관행렬은 대칭이어야 합니다.")
    finite = values[np.isfinite(values)]
    if np.isinf(values).any() or (finite.size and np.abs(finite).max() > 1 + 1e-10):
        raise ValueError("상관계수는 -1~1 또는 NaN이어야 합니다.")

    n, h = len(names), 1 / np.sqrt(2)
    norm = mpl.colors.Normalize(vmin=-1, vmax=1)
    color_map, gray_map = mpl.colormaps["RdBu_r"], mpl.colormaps["Greys"]
    style = {"font.family": "Malgun Gothic", "axes.unicode_minus": False,
             "svg.fonttype": "path", "figure.facecolor": "white", "axes.facecolor": "white"}

    with mpl.rc_context(style):
        fig = plt.figure(figsize=(24, 13.2), dpi=150)
        ax = fig.add_axes([0.025, 0.19, 0.95, 0.72])
        ax.set_aspect("equal")
        ax.set_axis_off()

        for i in range(1, n):
            for j in range(i):
                r = values[i, j]
                # 정사각 격자의 45도 회전: 맨 위에서 좌우로 펼쳐지는 삼각형.
                x, y = (i + j - n + 1) * h, (i - j) * h
                if np.isnan(r):
                    rgba = (0.95, 0.95, 0.95, 1)
                    number = "—"
                else:
                    rgba = color_map(norm(r)) if not highlight_target or i == n - 1 else gray_map(abs(r))
                    if highlight_target and i != n - 1:
                        rgba = tuple(0.18 + 0.82 * c for c in rgba[:3]) + (1,)
                    number = f"{0.0 if abs(r) < 0.005 else r:.2f}"
                cell = Polygon([(x, y + h), (x + h, y), (x, y - h), (x - h, y)],
                               facecolor=rgba, edgecolor="white", linewidth=0.85)
                cell.set_gid(f"cell:{i}:{j}")
                ax.add_patch(cell)
                rgb = np.asarray(rgba[:3])
                linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
                luminance = float(linear @ [0.2126, 0.7152, 0.0722])
                text_color = "#171717" if luminance > 0.20 else "white"
                text = ax.text(x, y, number, ha="center", va="center", rotation=0,
                               fontsize=14.5, color=text_color, zorder=3)
                text.set_gid(f"value:{i}:{j}")

        if highlight_target:
            # 종속변수 행 전체를 하나의 검은 평행사변형 테두리로 감싼다.
            outline = Polygon([(0, n * h), ((n - 1) * h, h),
                               ((n - 2) * h, 0), (-h, (n - 1) * h)],
                              fill=False, edgecolor="#111111", linewidth=2.6,
                              joinstyle="miter", zorder=4)
            outline.set_gid("target-outline")
            ax.add_patch(outline)

        labels, gap = [], 0.20
        # i=0 행에는 하삼각 셀이 없으므로 왼쪽 첫 변수 라벨을 만들지 않는다.
        for i in range(1, n):
            x, y = (i - n + 1) * h, i * h
            label = ax.text(x - h / 2 - gap, y + h / 2, display_names[i],
                            ha="right", va="center", rotation=0, fontsize=14.5,
                            color="#161616", fontweight="bold" if highlight_target and i == n - 1 else "normal")
            label.set_gid(f"left:{i}")
            labels.append(label)
        # 마지막 열에는 하삼각 셀이 없으므로 오른쪽 종속변수 라벨을 만들지 않는다.
        for j in range(n - 1):
            x, y = j * h, (n - 1 - j) * h
            label = ax.text(x + h / 2 + gap, y + h / 2, display_names[j],
                            ha="left", va="center", rotation=0, fontsize=14.5, color="#161616")
            label.set_gid(f"right:{j}")
            labels.append(label)

        ax.set_xlim(-(n - 1) * h - 5, (n - 1) * h + 5)
        ax.set_ylim(-0.6, n * h + 0.8)
        # 긴 원본 컬럼명도 자르지 않도록 실제 글자 폭으로 좌우 여백을 조정한다.
        for _ in range(10):
            fig.canvas.draw()
            renderer = fig.canvas.get_renderer()
            boxes = [label.get_window_extent(renderer).transformed(ax.transData.inverted())
                     for label in labels]
            limits = (min(box.x0 for box in boxes) - 0.30,
                      max(box.x1 for box in boxes) + 0.30)
            if np.allclose(ax.get_xlim(), limits, atol=0.01, rtol=0):
                break
            ax.set_xlim(*limits)

        # 범례를 삼각형 아래에 수평으로 놓아 양쪽 변수 라벨과 시각적 흐름을 맞춘다.
        cax = fig.add_axes([0.16, 0.105, 0.68, 0.026])
        colorbar = fig.colorbar(mpl.cm.ScalarMappable(norm=norm, cmap=color_map),
                                cax=cax, orientation="horizontal")
        colorbar.set_ticks(np.linspace(-1, 1, 9))
        colorbar.ax.xaxis.set_major_formatter(FormatStrFormatter("%.2f"))
        colorbar.ax.tick_params(labelsize=12.5, length=4, width=0.7, colors="#444444")
        colorbar.outline.set_edgecolor("#dddddd")
        colorbar.outline.set_linewidth(0.7)
        fig.suptitle(title, x=0.5, y=0.96, fontsize=24, fontweight="bold", color="#111111")

        if output_stem is not None:
            output_stem = Path(output_stem)
            output_stem.parent.mkdir(parents=True, exist_ok=True)
            for extension in ("png", "svg"):
                fig.savefig(output_stem.with_suffix(f".{extension}"), dpi=300,
                            facecolor="white", transparent=False)
        return fig, ax


if __name__ == "__main__":
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=project / "data/master/마스터테이블(가스 운반선).csv")
    parser.add_argument("--output", type=Path, default=project / "reports/figures" / FILENAME)
    args = parser.parse_args()
    data = pd.read_csv(args.csv, encoding="utf-8-sig")
    correlation = data[[*FEATURES, "수주용량"]].corr()
    figure, _ = draw_rotated_correlation(correlation, output_stem=args.output)
    plt.close(figure)
    print(f"저장 완료: {args.output}.png / {args.output}.svg")
