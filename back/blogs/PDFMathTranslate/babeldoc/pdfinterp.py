import logging
from collections.abc import Sequence
from typing import Any
from typing import cast

import numpy as np
from pdfminer import settings
from pdfminer.pdfcolor import PREDEFINED_COLORSPACE
from pdfminer.pdfcolor import PDFColorSpace
from pdfminer.pdfdevice import PDFDevice
from pdfminer.pdfdevice import PDFTextSeq
from pdfminer.pdffont import PDFFont
from pdfminer.pdfinterp import LITERAL_FORM
from pdfminer.pdfinterp import LITERAL_IMAGE
from pdfminer.pdfinterp import Color
from pdfminer.pdfinterp import PDFContentParser
from pdfminer.pdfinterp import PDFInterpreterError
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFStackT
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import PDFObjRef
from pdfminer.pdftypes import dict_value
from pdfminer.pdftypes import list_value
from pdfminer.pdftypes import resolve1
from pdfminer.pdftypes import stream_value
from pdfminer.psexceptions import PSEOF
from pdfminer.psparser import PSKeyword
from pdfminer.psparser import keyword_name
from pdfminer.psparser import literal_name
from pdfminer.utils import MATRIX_IDENTITY
from pdfminer.utils import Matrix
from pdfminer.utils import Rect
from pdfminer.utils import apply_matrix_pt
from pdfminer.utils import mult_matrix

from babeldoc.document_il.frontend.il_creater import ILCreater

log = logging.getLogger(__name__)


def safe_float(o: Any) -> float | None:
    try:
        return float(o)
    except (TypeError, ValueError):
        return None


class PDFPageInterpreterEx(PDFPageInterpreter):
    """Processor for the content of a PDF page

    Reference: PDF Reference, Appendix A, Operator Summary
    """

    def __init__(
        self,
        rsrcmgr: PDFResourceManager,
        device: PDFDevice,
        obj_patch,
        il_creater: ILCreater,
    ) -> None:
        self.rsrcmgr = rsrcmgr
        self.device = device
        self.obj_patch = obj_patch
        self.il_creater = il_creater

    def dup(self) -> "PDFPageInterpreterEx":
        return self.__class__(
            self.rsrcmgr,
            self.device,
            self.obj_patch,
            self.il_creater,
        )

    def init_resources(self, resources: dict[object, object]) -> None:
        # 重载设置 fontid 和 descent
        """Prepare the fonts and XObjects listed in the Resource attribute."""
        self.resources = resources
        self.fontmap: dict[object, PDFFont] = {}
        self.fontid: dict[PDFFont, object] = {}
        self.xobjmap = {}
        self.csmap: dict[str, PDFColorSpace] = PREDEFINED_COLORSPACE.copy()
        if not resources:
            return

        def get_colorspace(spec: object) -> PDFColorSpace | None:
            if isinstance(spec, list):
                name = literal_name(spec[0])
            else:
                name = literal_name(spec)
            if name == "ICCBased" and isinstance(spec, list) and len(spec) >= 2:
                return PDFColorSpace(name, stream_value(spec[1])["N"])
            elif name == "DeviceN" and isinstance(spec, list) and len(spec) >= 2:
                return PDFColorSpace(name, len(list_value(spec[1])))
            else:
                return PREDEFINED_COLORSPACE.get(name)

        for k, v in dict_value(resources).items():
            # log.debug("Resource: %r: %r", k, v)
            if k == "Font":
                for fontid, spec in dict_value(v).items():
                    objid = None
                    if isinstance(spec, PDFObjRef):
                        objid = spec.objid
                    spec = dict_value(spec)
                    font = self.rsrcmgr.get_font(objid, spec)
                    self.il_creater.on_page_resource_font(font, objid, fontid)
                    self.fontmap[fontid] = font
                    self.fontmap[fontid].descent = 0  # hack fix descent
                    self.fontid[self.fontmap[fontid]] = fontid
            elif k == "ColorSpace":
                for csid, spec in dict_value(v).items():
                    colorspace = get_colorspace(resolve1(spec))
                    if colorspace is not None:
                        self.csmap[csid] = colorspace
            elif k == "ProcSet":
                self.rsrcmgr.get_procset(list_value(v))
            elif k == "XObject":
                for xobjid, xobjstrm in dict_value(v).items():
                    self.xobjmap[xobjid] = xobjstrm
        pass

    def do_S(self) -> None:
        # 重载过滤非公式线条
        """Stroke path"""

        def is_black(color: Color) -> bool:
            if isinstance(color, tuple):
                return sum(color) == 0
            else:
                return color == 0

        if (
            len(self.curpath) == 2
            and self.curpath[0][0] == "m"
            and self.curpath[1][0] == "l"
            and apply_matrix_pt(self.ctm, self.curpath[0][-2:])[1]
            == apply_matrix_pt(self.ctm, self.curpath[1][-2:])[1]
            and is_black(self.graphicstate.scolor)
        ):  # 独立直线，水平，黑色
            # print(apply_matrix_pt(self.ctm,self.curpath[0][-2:]),apply_matrix_pt(self.ctm,self.curpath[1][-2:]),self.graphicstate.scolor)
            self.device.paint_path(self.graphicstate, True, False, False, self.curpath)
            self.curpath = []
            return "n"
        else:
            self.curpath = []

    def do_CS(self, name: PDFStackT) -> None:
        """Set color space for stroking operations

        Introduced in PDF 1.1
        """
        try:
            self.il_creater.on_stroking_color_space(literal_name(name))
            self.scs = self.csmap[literal_name(name)]
        except KeyError:
            if settings.STRICT:
                raise PDFInterpreterError(f"Undefined ColorSpace: {name!r}") from None
        return

    def do_cs(self, name: PDFStackT) -> None:
        """Set color space for nonstroking operations"""
        try:
            self.il_creater.on_non_stroking_color_space(literal_name(name))
            self.ncs = self.csmap[literal_name(name)]
        except KeyError:
            if settings.STRICT:
                raise PDFInterpreterError(f"Undefined ColorSpace: {name!r}") from None
        return

    ############################################################
    # 重载过滤非公式线条（F/B）
    def do_f(self) -> None:
        """Fill path using nonzero winding number rule"""
        # self.device.paint_path(self.graphicstate, False, True, False, self.curpath)
        self.curpath = []

    def do_F(self) -> None:
        """Fill path using nonzero winding number rule (obsolete)"""

    def do_f_a(self) -> None:
        """Fill path using even-odd rule"""
        # self.device.paint_path(self.graphicstate, False, True, True, self.curpath)
        self.curpath = []

    def do_B(self) -> None:
        """Fill and stroke path using nonzero winding number rule"""
        # self.device.paint_path(self.graphicstate, True, True, False, self.curpath)
        self.curpath = []

    def do_B_a(self) -> None:
        """Fill and stroke path using even-odd rule"""
        # self.device.paint_path(self.graphicstate, True, True, True, self.curpath)
        self.curpath = []

    ############################################################
    # 重载返回调用参数（SCN）
    def do_SCN(self) -> None:
        """Set color for stroking operations."""
        if self.scs:
            n = self.scs.ncomponents
        else:
            if settings.STRICT:
                raise PDFInterpreterError("No colorspace specified!")
            n = 1
        args = self.pop(n)
        self.il_creater.on_passthrough_per_char("SCN", args)
        self.graphicstate.scolor = cast(Color, args)
        return args

    def do_scn(self) -> None:
        """Set color for nonstroking operations"""
        if self.ncs:
            n = self.ncs.ncomponents
        else:
            if settings.STRICT:
                raise PDFInterpreterError("No colorspace specified!")
            n = 1
        args = self.pop(n)
        self.il_creater.on_passthrough_per_char("scn", args)
        self.graphicstate.ncolor = cast(Color, args)
        return args

    def do_SC(self) -> None:
        """Set color for stroking operations"""
        args = self.do_SCN()
        self.il_creater.remove_latest_passthrough_per_char_instruction()
        self.il_creater.on_passthrough_per_char("SC", args)
        return args

    def do_sc(self) -> None:
        """Set color for nonstroking operations"""
        args = self.do_scn()
        self.il_creater.remove_latest_passthrough_per_char_instruction()
        self.il_creater.on_passthrough_per_char("sc", args)
        return args

    def do_Do(self, xobjid_arg: PDFStackT) -> None:
        # 重载设置 xobj 的 obj_patch
        """Invoke named XObject"""
        xobjid = literal_name(xobjid_arg)
        try:
            xobj = stream_value(self.xobjmap[xobjid])
        except KeyError:
            if settings.STRICT:
                raise PDFInterpreterError(f"Undefined xobject id: {xobjid!r}") from None
            return
        # log.debug("Processing xobj: %r", xobj)
        subtype = xobj.get("Subtype")
        if subtype is LITERAL_FORM and "BBox" in xobj:
            interpreter = self.dup()

            # In extremely rare cases, a none might be mixed in the bbox, for example
            # /BBox [ 0 3.052 null 274.9 157.3 ]
            bbox = list(
                filter(lambda x: x is not None, cast(Rect, list_value(xobj["BBox"])))
            )

            matrix = cast(Matrix, list_value(xobj.get("Matrix", MATRIX_IDENTITY)))
            # According to PDF reference 1.7 section 4.9.1, XObjects in
            # earlier PDFs (prior to v1.2) use the page's Resources entry
            # instead of having their own Resources entry.
            xobjres = xobj.get("Resources")
            if xobjres:
                resources = dict_value(xobjres)
            else:
                resources = self.resources.copy()
            self.device.begin_figure(xobjid, bbox, matrix)
            ctm = mult_matrix(matrix, self.ctm)
            (x, y, x2, y2) = bbox
            (x, y) = apply_matrix_pt(ctm, (x, y))
            (x2, y2) = apply_matrix_pt(ctm, (x2, y2))
            x_id = self.il_creater.on_xobj_begin((x, y, x2, y2), xobj.objid)
            ctm_inv = np.linalg.inv(np.array(ctm[:4]).reshape(2, 2))
            np_version = np.__version__
            if np_version.split(".")[0] >= "2":
                pos_inv = -np.asmatrix(ctm[4:]) * ctm_inv
            else:
                pos_inv = -np.mat(ctm[4:]) * ctm_inv
            a, b, c, d = ctm_inv.reshape(4).tolist()
            e, f = pos_inv.tolist()[0]
            ops_base = interpreter.render_contents(
                resources,
                [xobj],
                ctm=ctm,
            )
            self.ncs = interpreter.ncs
            self.scs = interpreter.scs
            self.il_creater.on_xobj_end(
                x_id,
                f"q {ops_base}Q {a} {b} {c} {d} {e} {f} cm ",
            )
            try:  # 有的时候 form 字体加不上这里会烂掉
                self.device.fontid = interpreter.fontid
                self.device.fontmap = interpreter.fontmap
                ops_new = self.device.end_figure(xobjid)
                ctm_inv = np.linalg.inv(np.array(ctm[:4]).reshape(2, 2))
                np_version = np.__version__
                if np_version.split(".")[0] >= "2":
                    pos_inv = -np.asmatrix(ctm[4:]) * ctm_inv
                else:
                    pos_inv = -np.mat(ctm[4:]) * ctm_inv
                a, b, c, d = ctm_inv.reshape(4).tolist()
                e, f = pos_inv.tolist()[0]
                self.obj_patch[self.xobjmap[xobjid].objid] = (
                    f"q {ops_base}Q {a} {b} {c} {d} {e} {f} cm {ops_new}"
                )
            except Exception:
                pass
        elif subtype is LITERAL_IMAGE and "Width" in xobj and "Height" in xobj:
            self.device.begin_figure(xobjid, (0, 0, 1, 1), MATRIX_IDENTITY)
            self.device.render_image(xobjid, xobj)
            self.device.end_figure(xobjid)
        else:
            # unsupported xobject type.
            pass

    def process_page(self, page: PDFPage) -> None:
        # 重载设置 page 的 obj_patch
        # log.debug("Processing page: %r", page)
        # print(page.mediabox,page.cropbox)
        # (x0, y0, x1, y1) = page.mediabox
        (x0, y0, x1, y1) = page.cropbox
        if page.rotate == 90:
            ctm = (0, -1, 1, 0, -y0, x1)
        elif page.rotate == 180:
            ctm = (-1, 0, 0, -1, x1, y1)
        elif page.rotate == 270:
            ctm = (0, 1, -1, 0, y1, -x0)
        else:
            ctm = (1, 0, 0, 1, -x0, -y0)
        self.il_creater.on_page_start()
        self.il_creater.on_page_crop_box(x0, y0, x1, y1)
        self.device.begin_page(page, ctm)
        ops_base = self.render_contents(page.resources, page.contents, ctm=ctm)
        self.device.fontid = self.fontid
        self.device.fontmap = self.fontmap
        ops_new = self.device.end_page(page)
        # 上面渲染的时候会根据 cropbox 减掉页面偏移得到真实坐标，这里输出的时候需要用 cm 把页面偏移加回来
        self.obj_patch[page.page_xref] = (
            # f"q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}"  # ops_base 里可能有图，需要让 ops_new 里的文字覆盖在上面，使用 q/Q 重置位置矩阵
            ""
        )
        for obj in page.contents:
            self.obj_patch[obj.objid] = ""
        return ops_base

    def render_contents(
        self,
        resources: dict[object, object],
        streams: Sequence[object],
        ctm: Matrix = MATRIX_IDENTITY,
    ) -> None:
        # 重载返回指令流
        """Render the content streams.

        This method may be called recursively.
        """
        # log.debug(
        #     "render_contents: resources=%r, streams=%r, ctm=%r",
        #     resources,
        #     streams,
        #     ctm,
        # )
        self.init_resources(resources)
        self.init_state(ctm)
        return self.execute(list_value(streams))

    def do_q(self) -> None:
        """Save graphics state"""
        self.gstack.append(self.get_current_state())
        self.il_creater.push_passthrough_per_char_instruction()
        return

    def do_Q(self) -> None:
        """Restore graphics state"""
        if self.gstack:
            self.set_current_state(self.gstack.pop())
        self.il_creater.pop_passthrough_per_char_instruction()
        return

    def do_TJ(self, seq: PDFStackT) -> None:
        """Show text, allowing individual glyph positioning"""
        if self.textstate.font is None:
            if settings.STRICT:
                raise PDFInterpreterError("No font specified!")
            return
        assert self.ncs is not None
        gs = self.graphicstate.copy()
        gs.passthrough_instruction = (
            self.il_creater.passthrough_per_char_instruction.copy()
        )
        self.device.render_string(self.textstate, cast(PDFTextSeq, seq), self.ncs, gs)
        return

    # Run PostScript commands
    # The Do_xxx method is the method for executing corresponding postscript instructions
    def execute(self, streams: Sequence[object]) -> None:
        ops = ""
        for stream in streams:
            self.il_creater.on_new_stream()
            # 重载返回指令流
            try:
                parser = PDFContentParser([stream])
            except PSEOF:
                # empty page
                return
            while True:
                try:
                    (_, obj) = parser.nextobject()
                except PSEOF:
                    break
                if isinstance(obj, PSKeyword):
                    name = keyword_name(obj)
                    act_name = (
                        name.replace("*", "_a").replace('"', "_w").replace("'", "_q")
                    )
                    method = f"do_{act_name}"
                    if hasattr(self, method):
                        func = getattr(self, method)
                        nargs = func.__code__.co_argcount - 1
                        if nargs:
                            args = self.pop(nargs)
                            # log.debug("exec: %s %r", name, args)
                            if len(args) == nargs:
                                func(*args)
                                if self.il_creater.is_passthrough_per_char_operation(
                                    name,
                                ):
                                    self.il_creater.on_passthrough_per_char(name, args)
                                if name == "d":
                                    arg0 = f"[{' '.join(f'{arg}' for arg in args[0])}]"
                                    arg1 = args[1]
                                    ops += f"{arg0} {arg1} {name} "
                                elif not (
                                    name[0] == "T"
                                    or name
                                    in ['"', "'", "EI", "MP", "DP", "BMC", "BDC"]
                                ):  # 过滤 T 系列文字指令，因为 EI 的参数是 obj 所以也需要过滤（只在少数文档中画横线时使用），过滤 marked 系列指令
                                    p = " ".join(
                                        [
                                            (
                                                f"{x:f}"
                                                if isinstance(x, float)
                                                else str(x).replace("'", "")
                                            )
                                            for x in args
                                        ],
                                    )
                                    ops += f"{p} {name} "
                        else:
                            # log.debug("exec: %s", name)
                            targs = func()
                            if targs is None:
                                targs = []
                            if not (name[0] == "T" or name in ["BI", "ID", "EMC"]):
                                p = " ".join(
                                    [
                                        (
                                            f"{x:f}"
                                            if isinstance(x, float)
                                            else str(x).replace("'", "")
                                        )
                                        for x in targs
                                    ],
                                )
                                ops += f"{p} {name} "
                    elif settings.STRICT:
                        error_msg = f"Unknown operator: {name!r}"
                        raise PDFInterpreterError(error_msg)
                else:
                    self.push(obj)
            # print('REV DATA',ops)
        return ops
