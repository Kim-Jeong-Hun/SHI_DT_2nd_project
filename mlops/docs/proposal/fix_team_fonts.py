"""팀 최종본(10/07) 글꼴 레벨링 — 내용·배치는 그대로 두고 글꼴 지정만 바로잡는다.

- 모든 글자: latin · ea(한글) · cs 글꼴을 같은 Pretendard 굵기로 (한글 글꼴이 빠지면 테마 기본 = 맑은 고딕/Calibri 로 보임)
- 글꼴 미지정 · 맑은 고딕 → 리드 문장은 Pretendard Medium, 굵게 지정된 글자는 Pretendard(+Bold), 나머지 Pretendard
- 테마 major/minor 글꼴을 Pretendard 로
- 모든 단락 a:pPr 에 eaLnBrk="0" · hangingPunct="0" (한국어 어절 단위 줄바꿈)
사용: python fix_team_fonts.py <입력.pptx> <출력.pptx>
"""
import re
import sys
from collections import Counter

from lxml import etree
from pptx import Presentation
from pptx.util import Emu

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
Q = lambda t: f"{{{A}}}{t}"
BAD = {None, "Malgun Gothic", "맑은 고딕", "Calibri", "+mn-lt", "+mn-ea", "+mj-lt", "+mj-ea"}
src, dst = sys.argv[1], sys.argv[2]
prs = Presentation(src)
log = Counter()


def set_face(rpr, face):
    for tag in ("latin", "ea", "cs"):
        el = rpr.find(Q(tag))
        if el is None:
            el = etree.SubElement(rpr, Q(tag))
        el.set("typeface", face)
    # a:rPr 자식 순서: ln · fill · effect · highlight · uLnTx… · latin · ea · cs · sym · hlinkClick — latin/ea/cs 를 그 순서로 다시 놓는다
    kids = [rpr.find(Q(t)) for t in ("latin", "ea", "cs")]
    for k in kids:
        rpr.remove(k)
    anchor = None
    for t in ("sym", "hlinkClick", "hlinkMouseOver", "rtl", "extLst"):
        anchor = rpr.find(Q(t))
        if anchor is not None:
            break
    for k in kids:
        if anchor is not None:
            anchor.addprevious(k)
        else:
            rpr.append(k)


def fix_tf(tf, lead=False):
    for p in tf.paragraphs:
        ppr = p._p.find(Q("pPr"))
        if ppr is None:
            ppr = etree.Element(Q("pPr"))
            p._p.insert(0, ppr)
        ppr.set("eaLnBrk", "0")
        ppr.set("hangingPunct", "0")
        for r in p.runs:
            rpr = r._r.get_or_add_rPr()
            lat = rpr.find(Q("latin"))
            name = lat.get("typeface") if lat is not None else None
            if name in BAD:
                face = "Pretendard Medium" if lead else "Pretendard"
                log[f"{name} → {face}{' (굵게)' if r.font.bold else ''}"] += 1
            else:
                face = name
                ea = rpr.find(Q("ea"))
                if ea is None or ea.get("typeface") != name:
                    log[f"한글 글꼴 보충 {name}"] += 1
            set_face(rpr, face)
            if lead and rpr.find(Q('solidFill')) is None:   # 리드 문장 색을 다른 장과 같게
                f = etree.Element(Q('solidFill')); etree.SubElement(f, Q('srgbClr')).set('val', '4C525A'); rpr.insert(0, f); log['리드 문장 색 맞춤'] += 1
            if re.search('[가-힣]', r.text or ''):   # 한글이 든 글자는 언어를 한국어로 — 없으면 PowerPoint가 영문 규칙으로 어절 중간을 끊는다
                rpr.set('lang', 'ko-KR'); rpr.set('altLang', 'en-US'); log['언어 ko-KR 지정'] += 1
        end = p._p.find(Q("endParaRPr"))
        if end is not None:
            lat = end.find(Q("latin"))
            set_face(end, lat.get("typeface") if lat is not None and lat.get("typeface") not in BAD else ("Pretendard Medium" if lead else "Pretendard"))


for s in prs.slides:
    for sh in s.shapes:
        shapes = sh.shapes if sh.shape_type == 6 else [sh]   # 그룹 안까지
        for x in shapes:
            if x.has_text_frame:
                lead = abs(Emu(x.top).inches - 1.58) < .02 and abs(Emu(x.left).inches - 1.35) < .02
                fix_tf(x.text_frame, lead)
            if getattr(x, "has_table", False) and x.has_table:
                for row in x.table.rows:
                    for c in row.cells:
                        fix_tf(c.text_frame)

# 테마 기본 글꼴
for rel in prs.slide_masters[0].part.rels.values():
    if rel.reltype.endswith("/theme"):
        th = etree.fromstring(rel.target_part.blob)
        for tag in ("majorFont", "minorFont"):
            f = th.find(f".//{Q(tag)}")
            for t in ("latin", "ea"):
                f.find(Q(t)).set("typeface", "Pretendard")
        rel.target_part._blob = etree.tostring(th, xml_declaration=True, encoding="UTF-8", standalone=True)
        log["테마 글꼴 → Pretendard"] += 1
prs.save(dst)
for k, v in log.most_common():
    print(f"{v:4d}  {k}")
