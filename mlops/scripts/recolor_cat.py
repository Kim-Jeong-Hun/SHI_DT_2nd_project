"""삐용이 3D 텍스처 만들기 — Sketchfab 'cat Walk'(CC-BY 4.0, Erina eka syaharani) 텍스처를 삐용이처럼 바꾼다.

1) 주황 털 → 회갈색 고등어 무늬(밝기만 살리고 색을 다시 입힘), 2배 해상도로 키움
2) 얼굴: 삐용이 사진을 머리 앞면에 정사영으로 구워 넣는다(bake).
   모델의 두 눈·코끝과 사진의 두 눈·코를 맞추는 아핀 변환 → 텍셀마다 3D 위치를 구해 사진에서 색을 가져온다.
   눈알·입은 모델 형상을 쓰므로 사진의 눈 안쪽·입 아래는 가린다.
3) 눈알: 짙은 청회색 홍채 + 크고 둥근 동공 + 반사광(사진 속 아깽이 눈)
출력: serving/static/story/img/fun/biyong_fur.jpg
"""
import io
import json
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1] / "serving/static/story/img/fun"
PHOTO = Path.home() / "Downloads" / "삐용이.png"
# 사진 기준점(원본 1039×1033 픽셀): 보는 사람 기준 왼눈 · 오른눈 · 코
P_EYE_L, P_EYE_R, P_NOSE = (253, 413), (626, 460), (366, 586)
SCALE = 2  # 텍스처 해상도 배수

glb = (ROOT / "biyong_cat.glb").read_bytes()
JL = struct.unpack("<I", glb[12:16])[0]
J = json.loads(glb[20:20 + JL])
BIN = glb[20 + JL + 8:]
CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def acc(i):
    a = J["accessors"][i]; bv = J["bufferViews"][a["bufferView"]]
    dt = np.dtype(CT[a["componentType"]]); n = NC[a["type"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0); stride = bv.get("byteStride", dt.itemsize * n)
    rows = [np.frombuffer(BIN, dtype=dt, count=n, offset=off + k * stride) for k in range(a["count"])]
    out = np.array(rows)
    if a.get("normalized"):
        out = out.astype(np.float32) / np.iinfo(dt).max
    return out


def local(n):
    if "matrix" in n:
        return np.array(n["matrix"], np.float64).reshape(4, 4).T
    t = n.get("translation", [0, 0, 0]); r = n.get("rotation", [0, 0, 0, 1]); s = n.get("scale", [1, 1, 1])
    x, y, z, w = r
    R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                  [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                  [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
    M = np.eye(4); M[:3, :3] = R * np.array(s); M[:3, 3] = t
    return M


WORLD = {}
def walk(i, P):
    WORLD[i] = P @ local(J["nodes"][i])
    for c in J["nodes"][i].get("children", []):
        walk(c, WORLD[i])
for r0 in J["scenes"][J.get("scene", 0)]["nodes"]:
    walk(r0, np.eye(4))


def mesh_world(mesh_name):
    ni = next(i for i, n in enumerate(J["nodes"]) if "mesh" in n and J["meshes"][n["mesh"]]["name"] == mesh_name)
    node = J["nodes"][ni]; prim = J["meshes"][node["mesh"]]["primitives"][0]; at = prim["attributes"]
    P = acc(at["POSITION"]).astype(np.float64); N = acc(at["NORMAL"]).astype(np.float64); UV = acc(at["TEXCOORD_0"]).astype(np.float64)
    I = acc(prim["indices"]).reshape(-1, 3).astype(np.int64)
    Ph = np.c_[P, np.ones(len(P))]
    if "skin" in node:  # 바인드 포즈: Σ w · (관절 월드 · 역바인드) · p
        sk = J["skins"][node["skin"]]; IBM = acc(sk["inverseBindMatrices"]).reshape(-1, 4, 4).transpose(0, 2, 1)
        Mj = np.stack([WORLD[j] @ IBM[k] for k, j in enumerate(sk["joints"])])
        js = acc(at["JOINTS_0"]).astype(np.int64); ws = acc(at["WEIGHTS_0"]).astype(np.float64)
        ws = ws / np.maximum(ws.sum(1, keepdims=True), 1e-9)
        Wp = np.zeros((len(P), 3)); Wn = np.zeros((len(P), 3))
        for c in range(4):
            M = Mj[js[:, c]]
            Wp += ws[:, c:c + 1] * np.einsum("nij,nj->ni", M, Ph)[:, :3]
            Wn += ws[:, c:c + 1] * np.einsum("nij,nj->ni", M[:, :3, :3], N)
    else:
        M = WORLD[ni]; Wp = (Ph @ M.T)[:, :3]; Wn = N @ M[:3, :3].T
    Wn /= np.maximum(np.linalg.norm(Wn, axis=1, keepdims=True), 1e-9)
    return Wp, Wn, UV, I


# ── 1) 털 다시 칠하기 ──
bv = J["bufferViews"][J["images"][0]["bufferView"]]
tex = Image.open(io.BytesIO(BIN[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB")
tex = tex.resize((tex.width * SCALE, tex.height * SCALE), Image.LANCZOS)
a = np.asarray(tex).astype(np.float32) / 255
r, g, b = a[..., 0], a[..., 1], a[..., 2]
mx, mn = a.max(-1), a.min(-1); d = np.maximum(mx - mn, 1e-6); s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
Y = .299 * r + .587 * g + .114 * b
fur = (h > 8) & (h < 55) & (s > .12)
Lc = np.clip((Y - .5) * 1.22 + .5, 0, 1)
xs = np.array([0, .32, .55, .78, 1.0])
cs = np.array([(.12, .10, .09), (.31, .27, .24), (.54, .49, .44), (.81, .77, .71), (.95, .93, .89)], np.float32)
out = a.copy()
for c in range(3):
    out[..., c] = np.where(fur, np.interp(Lc, xs, cs[:, c]), a[..., c])
H, W = Y.shape

# ── 2) 얼굴 굽기 ──
Bp, Bn, Buv, Bi = mesh_world("Mesh.002")
Ep, En, Euv, Ei = mesh_world("Mesh.003_0")
# 눈알: Mesh.003(눈·귀·이빨·수염)에서 홍채 텍스처(오른쪽 아래 원)를 쓰는 정점 = 눈
eye = (np.abs(Euv[:, 0] * 512 - 440) < 70) & (np.abs(Euv[:, 1] * 1024 - 940) < 70)
eyeL = Ep[eye & (Ep[:, 0] < 0)].mean(0); eyeR = Ep[eye & (Ep[:, 0] > 0)].mean(0)
head = (Bp[:, 2] > .78) & (Bp[:, 1] > -.2)
nose = Bp[head][np.argmax(Bp[head][:, 2])]
print("model eyes", eyeL.round(3), eyeR.round(3), "nose", nose.round(3), "head verts", int(head.sum()))
# 모델(x,y) → 사진(px) 아핀: 보는 사람 기준 왼눈 = 모델 -x
Msrc = np.array([[eyeL[0], eyeL[1], 1], [eyeR[0], eyeR[1], 1], [nose[0], nose[1], 1]])
A = np.linalg.solve(Msrc, np.array([P_EYE_L, P_EYE_R, P_NOSE], np.float64))  # 3×2

ph = Image.open(PHOTO).convert("RGB")
pa = np.asarray(ph).astype(np.float32) / 255
PH, PW = pa.shape[:2]
# 사진 마스크: 얼굴 타원 안 · 입(y>655) 아래 제외 · 눈알 자리는 모델 눈을 쓰므로 비움 · 가장자리 부드럽게
mk = Image.new("L", (PW, PH), 0); dr = ImageDraw.Draw(mk)
dr.ellipse((440 - 370, 470 - 360, 440 + 370, 470 + 330), fill=255)
dr.rectangle((0, 655, PW, PH), fill=0)
for ex, ey in (P_EYE_L, P_EYE_R):
    dr.ellipse((ex - 62, ey - 52, ex + 62, ey + 52), fill=0)
mk = np.asarray(mk.filter(ImageFilter.GaussianBlur(26))).astype(np.float32) / 255


def sample(img, x, y):
    x = np.clip(x, 0, img.shape[1] - 1.001); y = np.clip(y, 0, img.shape[0] - 1.001)
    x0 = x.astype(int); y0 = y.astype(int); fx = x - x0; fy = y - y0
    if img.ndim == 2:
        img = img[..., None]
    return (img[y0, x0] * ((1 - fx) * (1 - fy))[:, None] + img[y0, x0 + 1] * (fx * (1 - fy))[:, None]
            + img[y0 + 1, x0] * ((1 - fx) * fy)[:, None] + img[y0 + 1, x0 + 1] * (fx * fy)[:, None])


tri = Bi[head[Bi].all(1)]
acc_w = np.zeros((H, W)); acc_c = np.zeros((H, W, 3))
for t in tri:
    uv = Buv[t] * [W, H]
    x0, y0 = np.floor(uv.min(0)).astype(int); x1, y1 = np.ceil(uv.max(0)).astype(int)
    if x1 - x0 > W / 3:
        continue
    gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
    p = np.c_[gx.ravel(), gy.ravel()]
    T = np.array([uv[1] - uv[0], uv[2] - uv[0]]).T
    if abs(np.linalg.det(T)) < 1e-9:
        continue
    l12 = np.linalg.solve(T, (p - uv[0]).T).T; l0 = 1 - l12.sum(1)
    inside = (l0 >= -.01) & (l12[:, 0] >= -.01) & (l12[:, 1] >= -.01)
    if not inside.any():
        continue
    L = np.c_[l0, l12][inside]; q = p[inside]
    P3 = L @ Bp[t]; N3 = L @ Bn[t]; N3 /= np.linalg.norm(N3, axis=1, keepdims=True)
    face = np.clip((N3[:, 2] - .2) / .45, 0, 1)
    pp = np.c_[P3[:, :2], np.ones(len(P3))] @ A
    col = sample(pa, pp[:, 0], pp[:, 1]); m = sample(mk, pp[:, 0], pp[:, 1])[:, 0]
    w = face * m * .93
    xi = np.clip(q[:, 0].astype(int), 0, W - 1); yi = np.clip(q[:, 1].astype(int), 0, H - 1)
    acc_w[yi, xi] = np.maximum(acc_w[yi, xi], w); acc_c[yi, xi] = col
w3 = acc_w[..., None]
# 사진 밝기를 털 텍스처에 맞춘다(조명은 3D에서 다시 들어가므로 살짝 낮춤)
out = out * (1 - w3) + np.clip(acc_c * .9, 0, 1) * w3
print("baked texels", int((acc_w > .05).sum()))

# ── 3) 눈알: 짙은 청회색 홍채 + 둥근 큰 동공 + 반사광 ──
cx, cy, R0 = 440 * SCALE, 940 * SCALE, 52 * SCALE
yy, xx = np.mgrid[0:H, 0:W]; rr = np.hypot(xx - cx, yy - cy)
iris = rr < R0
t = np.clip(rr / R0, 0, 1)[..., None]
irc = np.array([.24, .33, .42]) * (1 - t) + np.array([.42, .52, .60]) * t
out[iris] = irc[iris]
out[rr < R0 * .57] = np.array([.03, .035, .045])   # 동공을 살짝 키워 아깽이처럼
out[np.hypot(xx - (cx - R0 * .28), yy - (cy - R0 * .30)) < R0 * .16] = np.array([.95, .97, 1.0])
out[np.hypot(xx - (cx + R0 * .26), yy - (cy + R0 * .24)) < R0 * .07] = np.array([.85, .9, .95])   # 작은 두 번째 반사광
ring = (rr >= R0 * .96) & (rr < R0 * 1.06)
out[ring] = out[ring] * .35

# 코: 사진처럼 짙은 갈흑색 — 얼굴 굽기에서 덮이지 않은 분홍을 정리
r, g, b = out[..., 0], out[..., 1], out[..., 2]
pinkn = (r > g + .12) & (r > b + .06) & (yy < 300 * SCALE) & (xx < 210 * SCALE) & (yy > 80 * SCALE)
out[pinkn] = out[pinkn] * np.array([.42, .36, .36])

Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(ROOT / "biyong_fur.jpg", quality=92)
print("ok", ROOT / "biyong_fur.jpg")
