"""'cat Walk'(CC-BY 4.0, Erina eka syaharani) 모델을 아깽이 얼굴로 다듬는다 → serving/static/story/img/fun/biyong_cat.glb

- 눈 둘레 피부를 바깥으로 밀어 눈구멍을 키움(귀여움 필터처럼 부드럽게 감쇠)
- 눈알을 키움(가로·세로 1.3배, 깊이 1.1배)
- 주둥이를 살짝 넣어 얼굴을 둥글게
- 귀를 1.15배(새끼 고양이는 귀가 커 보인다)
바인드 포즈 월드 좌표에서 변형한 뒤 각 정점의 (가중) 관절 행렬 역으로 되돌려 원래 공간에 쓴다.
"""
import json
import struct
from pathlib import Path

import numpy as np

SRC = Path.home() / "Downloads" / "cat_walk.glb"
DST = Path(__file__).resolve().parents[1] / "serving/static/story/img/fun/biyong_cat.glb"
EYE_K, EYE_R = .42, .075          # 눈구멍 확대 세기 · 반경(모델 단위)
EYEBALL = (1.3, 1.3, 1.1)
MUZZLE = .022
EAR = 1.15

glb = bytearray(SRC.read_bytes())
JL = struct.unpack("<I", glb[12:16])[0]
J = json.loads(bytes(glb[20:20 + JL]))
B0 = 20 + JL + 8
CT = {5126: np.float32, 5123: np.uint16, 5125: np.uint32, 5121: np.uint8}
NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def acc(i):
    a = J["accessors"][i]; bv = J["bufferViews"][a["bufferView"]]
    dt = np.dtype(CT[a["componentType"]]); n = NC[a["type"]]
    off = B0 + bv.get("byteOffset", 0) + a.get("byteOffset", 0); stride = bv.get("byteStride", dt.itemsize * n)
    out = np.array([np.frombuffer(glb, dtype=dt, count=n, offset=off + k * stride) for k in range(a["count"])])
    if a.get("normalized"):
        out = out.astype(np.float32) / np.iinfo(dt).max
    return out, off, stride


def put(i, arr):
    _, off, stride = acc(i)
    a = J["accessors"][i]
    for k, row in enumerate(arr.astype(np.float32)):
        glb[off + k * stride: off + k * stride + 12] = row.tobytes()
    a["min"] = arr.min(0).astype(float).tolist(); a["max"] = arr.max(0).astype(float).tolist()


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


def node_of(name):
    return next(i for i, n in enumerate(J["nodes"]) if "mesh" in n and J["meshes"][n["mesh"]]["name"] == name)


def per_vertex_mats(ni):
    node = J["nodes"][ni]; at = J["meshes"][node["mesh"]]["primitives"][0]["attributes"]
    P, _, _ = acc(at["POSITION"])
    if "skin" not in node:
        return np.repeat(WORLD[ni][None], len(P), 0), P.astype(np.float64), at
    sk = J["skins"][node["skin"]]; IBM = acc(sk["inverseBindMatrices"])[0].reshape(-1, 4, 4).transpose(0, 2, 1)
    Mj = np.stack([WORLD[j] @ IBM[k] for k, j in enumerate(sk["joints"])])
    js = acc(at["JOINTS_0"])[0].astype(np.int64); ws = acc(at["WEIGHTS_0"])[0].astype(np.float64)
    ws = ws / np.maximum(ws.sum(1, keepdims=True), 1e-9)
    M = np.einsum("nc,ncij->nij", ws, Mj[js])
    return M, P.astype(np.float64), at


def to_world(M, P):
    return np.einsum("nij,nj->ni", M, np.c_[P, np.ones(len(P))])[:, :3]


def to_local(M, Wp):
    return np.einsum("nij,nj->ni", np.linalg.inv(M), np.c_[Wp, np.ones(len(Wp))])[:, :3]


# 눈알·귀 = Mesh.003_0(강체), 얼굴 피부 = Mesh.002(스킨)
ni_e = node_of("Mesh.003_0"); Me, Pe, ate = per_vertex_mats(ni_e); We = to_world(Me, Pe)
UVe, _, _ = acc(ate["TEXCOORD_0"])
eye = (np.abs(UVe[:, 0] * 512 - 440) < 75) & (np.abs(UVe[:, 1] * 1024 - 940) < 75)
centers = [We[eye & (We[:, 0] < 0)].mean(0), We[eye & (We[:, 0] > 0)].mean(0)]
for c, side in zip(centers, (We[:, 0] < 0, We[:, 0] > 0)):
    sel = eye & side
    We[sel] = c + (We[sel] - c) * np.array(EYEBALL)
ear = (~eye) & (We[:, 1] > .27) & (np.abs(We[:, 0]) > .05)
for side in (We[:, 0] < 0, We[:, 0] > 0):
    sel = ear & side
    base = We[sel].copy(); base_c = np.array([base[:, 0].mean(), base[:, 1].min(), base[:, 2].mean()])
    We[sel] = base_c + (We[sel] - base_c) * EAR
put(ate["POSITION"], to_local(Me, We))

ni_b = node_of("Mesh.002"); Mb, Pb, atb = per_vertex_mats(ni_b); Wb = to_world(Mb, Pb)
front = Wb[:, 2] > 1.0
for c in centers:
    dxy = Wb[:, :2] - c[:2]; d = np.linalg.norm(dxy, axis=1)
    f = np.clip(1 - (d / EYE_R) ** 2, 0, 1) ** 2 * front
    Wb[:, :2] += dxy * (EYE_K * f)[:, None]
mz = (Wb[:, 2] > 1.12) & (Wb[:, 1] < .17)
Wb[mz, 2] -= MUZZLE * np.clip((Wb[mz, 2] - 1.12) / .1, 0, 1)
put(atb["POSITION"], to_local(Mb, Wb))

# JSON 길이는 그대로(min/max 숫자만 바뀜) — 다시 직렬화해 4바이트 정렬로 채운다
js = json.dumps(J, separators=(",", ":")).encode()
js += b" " * ((4 - len(js) % 4) % 4)
binchunk = bytes(glb[20 + JL:])
out = bytearray(b"glTF") + struct.pack("<II", 2, 12 + 8 + len(js) + len(binchunk)) + struct.pack("<I", len(js)) + b"JSON" + js + binchunk
DST.write_bytes(out)
print("ok", DST, "eyes", [c.round(3).tolist() for c in centers], "eyeball verts", int(eye.sum()), "ear verts", int(ear.sum()))
