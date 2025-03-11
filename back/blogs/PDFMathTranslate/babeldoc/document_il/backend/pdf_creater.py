import logging
import os
import re
import time
from multiprocessing import Process
from pathlib import Path

import pymupdf
from bitstring import BitStream

from babeldoc.document_il import il_version_1
from babeldoc.document_il.utils.fontmap import FontMapper
from babeldoc.translation_config import TranslateResult
from babeldoc.translation_config import TranslationConfig
from babeldoc.translation_config import WatermarkOutputMode

logger = logging.getLogger(__name__)

SUBSET_FONT_STAGE_NAME = "Subset font"
SAVE_PDF_STAGE_NAME = "Save PDF"


def _subset_fonts_process(pdf_path, output_path):
    """Function to run in subprocess for font subsetting.

    Args:
        pdf_path: Path to the PDF file to subset
        output_path: Path where to save the result
    """
    try:
        pdf = pymupdf.open(pdf_path)
        pdf.subset_fonts(fallback=False)
        pdf.save(output_path)
        # 返回0表示成功
        os._exit(0)
    except Exception as e:
        logger.error(f"Error in font subsetting subprocess: {e}")
        # 返回1表示失败
        os._exit(1)


def _save_pdf_clean_process(
    pdf_path,
    output_path,
    garbage=1,
    deflate=True,
    clean=True,
    deflate_fonts=True,
    linear=False,
):
    """Function to run in subprocess for saving PDF with clean=True which can be time-consuming.

    Args:
        pdf_path: Path to the PDF file to save
        output_path: Path where to save the result
        garbage: Garbage collection level (0, 1, 2, 3, 4)
        deflate: Whether to deflate the PDF
        clean: Whether to clean the PDF
        deflate_fonts: Whether to deflate fonts
        linear: Whether to linearize the PDF
    """
    try:
        pdf = pymupdf.open(pdf_path)
        pdf.save(
            output_path,
            garbage=garbage,
            deflate=deflate,
            clean=clean,
            deflate_fonts=deflate_fonts,
            linear=linear,
        )
        # 返回0表示成功
        os._exit(0)
    except Exception as e:
        logger.error(f"Error in save PDF with clean=True subprocess: {e}")
        # 返回1表示失败
        os._exit(1)


class PDFCreater:
    stage_name = "Generate drawing instructions"

    def __init__(
        self,
        original_pdf_path: str,
        document: il_version_1.Document,
        translation_config: TranslationConfig,
    ):
        self.original_pdf_path = original_pdf_path
        self.docs = document
        self.font_path = translation_config.font
        self.font_mapper = FontMapper(translation_config)
        self.translation_config = translation_config

    def render_graphic_state(
        self,
        draw_op: BitStream,
        graphic_state: il_version_1.GraphicState,
    ):
        if graphic_state is None:
            return
        # if graphic_state.stroking_color_space_name:
        #     draw_op.append(
        #         f"/{graphic_state.stroking_color_space_name} CS \n".encode()
        #     )
        # if graphic_state.non_stroking_color_space_name:
        #     draw_op.append(
        #         f"/{graphic_state.non_stroking_color_space_name}"
        #         f" cs \n".encode()
        #     )
        # if graphic_state.ncolor is not None:
        #     if len(graphic_state.ncolor) == 1:
        #         draw_op.append(f"{graphic_state.ncolor[0]} g \n".encode())
        #     elif len(graphic_state.ncolor) == 3:
        #         draw_op.append(
        #             f"{' '.join((str(x) for x in graphic_state.ncolor))} sc \n".encode()
        #         )
        # if graphic_state.scolor is not None:
        #     if len(graphic_state.scolor) == 1:
        #         draw_op.append(f"{graphic_state.scolor[0]} G \n".encode())
        #     elif len(graphic_state.scolor) == 3:
        #         draw_op.append(
        #             f"{' '.join((str(x) for x in graphic_state.scolor))} SC \n".encode()
        #         )

        if graphic_state.passthrough_per_char_instruction:
            draw_op.append(
                f"{graphic_state.passthrough_per_char_instruction} \n".encode(),
            )

    def render_paragraph_to_char(
        self,
        paragraph: il_version_1.PdfParagraph,
    ) -> list[il_version_1.PdfCharacter]:
        chars = []
        for composition in paragraph.pdf_paragraph_composition:
            if not isinstance(composition.pdf_character, il_version_1.PdfCharacter):
                logger.error(
                    f"Unknown composition type. "
                    f"This type only appears in the IL "
                    f"after the translation is completed."
                    f"During pdf rendering, this type is not supported."
                    f"Composition: {composition}. "
                    f"Paragraph: {paragraph}. ",
                )
                continue
            chars.append(composition.pdf_character)
        if not chars and paragraph.unicode:
            logger.error(
                f"Unable to export paragraphs that have "
                f"not yet been formatted: {paragraph}",
            )
            return chars
        return chars

    def get_available_font_list(self, pdf, page):
        page_xref_id = pdf[page.page_number].xref
        return self.get_xobj_available_fonts(page_xref_id, pdf)

    def get_xobj_available_fonts(self, page_xref_id, pdf):
        resources_type, r_id = pdf.xref_get_key(page_xref_id, "Resources")
        if resources_type == "xref":
            resource_xref_id = re.search("(\\d+) 0 R", r_id).group(1)
            r_id = pdf.xref_object(int(resource_xref_id))
            resources_type = "dict"
        if resources_type == "dict":
            xref_id = re.search("/Font (\\d+) 0 R", r_id)
            if xref_id is not None:
                xref_id = xref_id.group(1)
                font_dict = pdf.xref_object(int(xref_id))
            else:
                search = re.search("/Font *<<(.+?)>>", r_id.replace("\n", " "))
                if search is None:
                    # Have resources but no fonts
                    return set()
                font_dict = search.group(1)
        else:
            r_id = int(r_id.split(" ")[0])
            _, font_dict = pdf.xref_get_key(r_id, "Font")
        fonts = re.findall("/([^ ]+?) ", font_dict)
        return set(fonts)

    def _debug_render_rectangle(
        self,
        draw_op: BitStream,
        rectangle: il_version_1.PdfRectangle,
    ):
        """Draw a debug rectangle in PDF for visualization purposes.

        Args:
            draw_op: BitStream to append PDF drawing operations
            rectangle: Rectangle object containing position information
        """
        x1 = rectangle.box.x
        y1 = rectangle.box.y
        x2 = rectangle.box.x2
        y2 = rectangle.box.y2
        # Save graphics state
        draw_op.append(b"q ")

        # Set green color for debug visibility
        draw_op.append(
            rectangle.graphic_state.passthrough_per_char_instruction.encode(),
        )  # Green stroke
        draw_op.append(b" 1 w ")  # Line width

        # Draw four lines manually
        # Bottom line
        draw_op.append(f"{x1} {y1} m {x2} {y1} l S ".encode())
        # Right line
        draw_op.append(f"{x2} {y1} m {x2} {y2} l S ".encode())
        # Top line
        draw_op.append(f"{x2} {y2} m {x1} {y2} l S ".encode())
        # Left line
        draw_op.append(f"{x1} {y2} m {x1} {y1} l S ".encode())

        # Restore graphics state
        draw_op.append(b"Q\n")

    def create_side_by_side_dual_pdf(
        self,
        original_pdf: pymupdf.Document,
        translated_pdf: pymupdf.Document,
        dual_out_path: str,
        translation_config: TranslationConfig,
    ) -> pymupdf.Document:
        """Create a dual PDF with side-by-side pages (original and translation).

        Args:
            original_pdf: Original PDF document
            translated_pdf: Translated PDF document
            dual_out_path: Output path for the dual PDF
            translation_config: Translation configuration

        Returns:
            The created dual PDF document
        """
        # Create a new PDF for side-by-side pages
        dual = pymupdf.open()
        page_count = min(original_pdf.page_count, translated_pdf.page_count)

        for page_id in range(page_count):
            # Get pages from both PDFs
            orig_page = original_pdf[page_id]
            trans_page = translated_pdf[page_id]

            # Calculate total width and use max height
            total_width = orig_page.rect.width + trans_page.rect.width
            max_height = max(orig_page.rect.height, trans_page.rect.height)

            # Create new page with combined width
            dual_page = dual.new_page(width=total_width, height=max_height)

            # Define rectangles for left and right sides
            left_width = (
                orig_page.rect.width
                if not translation_config.dual_translate_first
                else trans_page.rect.width
            )
            rect_left = pymupdf.Rect(0, 0, left_width, max_height)
            rect_right = pymupdf.Rect(left_width, 0, total_width, max_height)

            # Show pages according to dual_translate_first setting
            if translation_config.dual_translate_first:
                # Show translated page on left and original on right
                rect_left, rect_right = rect_right, rect_left
            try:
                # Show original page on left and translated on right (default)
                dual_page.show_pdf_page(
                    rect_left,
                    original_pdf,
                    page_id,
                    keep_proportion=True,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to show original page on left and translated on right (default). "
                    f"Page ID: {page_id}. "
                    f"Original PDF: {self.original_pdf_path}. "
                    f"Translated PDF: {translation_config.input_file}. ",
                    exc_info=e,
                )
            try:
                dual_page.show_pdf_page(
                    rect_right,
                    translated_pdf,
                    page_id,
                    keep_proportion=True,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to show translated page on left and original on right. "
                    f"Page ID: {page_id}. "
                    f"Original PDF: {self.original_pdf_path}. "
                    f"Translated PDF: {translation_config.input_file}. ",
                    exc_info=e,
                )
        return dual

    def create_alternating_pages_dual_pdf(
        self,
        original_pdf_path: str,
        translated_pdf: pymupdf.Document,
        translation_config: TranslationConfig,
    ) -> pymupdf.Document:
        """Create a dual PDF with alternating pages (original and translation).

        Args:
            original_pdf_path: Path to the original PDF
            translated_pdf: Translated PDF document
            translation_config: Translation configuration

        Returns:
            The created dual PDF document
        """
        # Open the original PDF and insert translated PDF
        dual = pymupdf.open(original_pdf_path)
        dual.insert_file(translated_pdf)

        # Rearrange pages to alternate between original and translated
        page_count = translated_pdf.page_count
        for page_id in range(page_count):
            if translation_config.dual_translate_first:
                dual.move_page(page_count + page_id, page_id * 2)
            else:
                dual.move_page(page_count + page_id, page_id * 2 + 1)

        return dual

    def write_debug_info(
        self,
        pdf: pymupdf.Document,
        translation_config: TranslationConfig,
    ):
        self.font_mapper.add_font(pdf, self.docs)

        for page in self.docs.page:
            _, r_id = pdf.xref_get_key(pdf[page.page_number].xref, "Contents")
            resource_xref_id = re.search("(\\d+) 0 R", r_id).group(1)
            base_op = pdf.xref_stream(int(resource_xref_id))
            translation_config.raise_if_cancelled()
            xobj_available_fonts = {}
            xobj_draw_ops = {}
            xobj_encoding_length_map = {}
            available_font_list = self.get_available_font_list(pdf, page)

            page_encoding_length_map = {
                f.font_id: f.encoding_length for f in page.pdf_font
            }
            page_op = BitStream()
            # q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}
            page_op.append(b"q ")
            if base_op is not None:
                page_op.append(base_op)
            page_op.append(b" Q ")
            page_op.append(
                f"q Q 1 0 0 1 {page.cropbox.box.x} {page.cropbox.box.y} cm \n".encode(),
            )
            # 收集所有字符
            chars = []
            # 首先添加页面级别的字符
            if page.pdf_character:
                chars.extend(page.pdf_character)
            # 然后添加段落中的字符
            for paragraph in page.pdf_paragraph:
                chars.extend(self.render_paragraph_to_char(paragraph))

            # 渲染所有字符
            for char in chars:
                if not getattr(char, "debug_info", False):
                    continue
                if char.char_unicode == "\n":
                    continue
                if char.pdf_character_id is None:
                    # dummy char
                    continue
                char_size = char.pdf_style.font_size
                font_id = char.pdf_style.font_id

                if font_id not in available_font_list:
                    continue
                draw_op = page_op
                encoding_length_map = page_encoding_length_map

                draw_op.append(b"q ")
                self.render_graphic_state(draw_op, char.pdf_style.graphic_state)
                if char.vertical:
                    draw_op.append(
                        f"BT /{font_id} {char_size:f} Tf 0 1 -1 0 {char.box.x2:f} {char.box.y:f} Tm ".encode(),
                    )
                else:
                    draw_op.append(
                        f"BT /{font_id} {char_size:f} Tf 1 0 0 1 {char.box.x:f} {char.box.y:f} Tm ".encode(),
                    )

                encoding_length = encoding_length_map[font_id]
                # pdf32000-2008 page14:
                # As hexadecimal data enclosed in angle brackets < >
                # see 7.3.4.3, "Hexadecimal Strings."
                draw_op.append(
                    f"<{char.pdf_character_id:0{encoding_length * 2}x}>".upper().encode(),
                )

                draw_op.append(b" Tj ET Q \n")
            for rect in page.pdf_rectangle:
                if not rect.debug_info:
                    continue
                self._debug_render_rectangle(page_op, rect)
            draw_op = page_op
            # Since this is a draw instruction container,
            # no additional information is needed
            pdf.update_stream(int(resource_xref_id), draw_op.tobytes())
        translation_config.raise_if_cancelled()

        # 使用子进程进行字体子集化
        if not translation_config.skip_clean:
            pdf = self.subset_fonts_in_subprocess(pdf, translation_config, tag="debug")
        return pdf

    @staticmethod
    def subset_fonts_in_subprocess(
        pdf: pymupdf.Document, translation_config: TranslationConfig, tag: str
    ) -> pymupdf.Document:
        """Run font subsetting in a subprocess with timeout.

        Args:
            pdf: The PDF document object
            translation_config: Translation configuration

        Returns:
            Path to the PDF with subsetted fonts, or original path if subsetting failed or timed out
        """
        original_pdf = pdf
        # Create temporary file paths
        temp_input = str(
            translation_config.get_working_file_path(f"temp_subset_input_{tag}.pdf")
        )
        temp_output = str(
            translation_config.get_working_file_path(f"temp_subset_output_{tag}.pdf")
        )

        # Save PDF to temporary file without subsetting
        pdf.save(temp_input)

        # Create and start subprocess
        process = Process(target=_subset_fonts_process, args=(temp_input, temp_output))
        process.start()

        # Wait for subprocess with timeout (1 minute)
        timeout = 60  # 1 minutes in seconds
        start_time = time.time()

        while process.is_alive():
            if time.time() - start_time > timeout:
                logger.warning(
                    f"Font subsetting timeout after {timeout} seconds, terminating subprocess"
                )
                process.terminate()
                try:
                    process.join(5)  # Give it 5 seconds to clean up
                    if process.is_alive():
                        logger.warning("Subprocess did not terminate, killing it")
                        process.kill()
                        process.terminate()
                        process.kill()
                        process.terminate()
                        process.kill()
                        process.terminate()
                except Exception as e:
                    logger.error(f"Error terminating font subsetting process: {e}")

                return original_pdf

            time.sleep(0.5)  # Check every half second

        # Process completed, check exit code
        exit_code = process.exitcode
        success = exit_code == 0

        # Check if subsetting was successful
        if (
            success
            and Path(temp_output).exists()
            and Path(temp_output).stat().st_size > 0
        ):
            logger.info("Font subsetting completed successfully")
            return pymupdf.open(temp_output)
        else:
            logger.warning(
                f"Font subsetting failed with exit code {exit_code} or produced empty file"
            )
            return original_pdf

    @staticmethod
    def save_pdf_with_timeout(
        pdf: pymupdf.Document,
        output_path: str,
        translation_config: TranslationConfig,
        garbage: int = 1,
        deflate: bool = True,
        clean: bool = True,
        deflate_fonts: bool = True,
        linear: bool = False,
        timeout: int = 120,
        tag: str = "",
    ) -> bool:
        """Save a PDF document with a timeout for the clean=True operation.

        Args:
            pdf: The PDF document object
            output_path: Path where to save the PDF
            translation_config: Translation configuration
            garbage: Garbage collection level (0, 1, 2, 3, 4)
            deflate: Whether to deflate the PDF
            clean: Whether to clean the PDF
            deflate_fonts: Whether to deflate fonts
            linear: Whether to linearize the PDF
            timeout: Timeout in seconds (default: 2 minutes)

        Returns:
            True if saved with clean=True successfully, False if fallback to clean=False was used
        """
        # Create temporary file paths
        temp_input = str(
            translation_config.get_working_file_path(f"temp_save_input_{tag}.pdf")
        )
        temp_output = str(
            translation_config.get_working_file_path(f"temp_save_output_{tag}.pdf")
        )

        # Save PDF to temporary file first
        pdf.save(temp_input)

        # Try to save with clean=True in a subprocess
        process = Process(
            target=_save_pdf_clean_process,
            args=(
                temp_input,
                temp_output,
                garbage,
                deflate,
                clean,
                deflate_fonts,
                linear,
            ),
        )
        process.start()

        # Wait for subprocess with timeout
        start_time = time.time()

        while process.is_alive():
            if time.time() - start_time > timeout:
                logger.warning(
                    f"PDF save with clean=True timeout after {timeout} seconds, terminating subprocess"
                )
                process.terminate()
                try:
                    process.join(5)  # Give it 5 seconds to clean up
                    if process.is_alive():
                        logger.warning("Subprocess did not terminate, killing it")
                        process.kill()
                        process.terminate()
                        process.kill()
                        process.terminate()
                        process.kill()
                        process.terminate()
                except Exception as e:
                    logger.error(f"Error terminating PDF save process: {e}")

                # Fallback to save without clean parameter
                logger.info("Falling back to save without clean=True")
                try:
                    pdf.save(
                        output_path,
                        garbage=garbage,
                        deflate=deflate,
                        clean=False,
                        deflate_fonts=deflate_fonts,
                        linear=linear,
                    )
                    return False
                except Exception as e:
                    logger.error(f"Error in fallback save: {e}")
                    # Last resort: basic save
                    pdf.save(output_path)
                    return False

            time.sleep(0.5)  # Check every half second

        # Process completed, check exit code
        exit_code = process.exitcode
        success = exit_code == 0

        # Check if save was successful
        if (
            success
            and Path(temp_output).exists()
            and Path(temp_output).stat().st_size > 0
        ):
            logger.info("PDF save with clean=True completed successfully")
            # Copy the successfully created file to the target path
            try:
                import shutil

                shutil.copy2(temp_output, output_path)
                return True
            except Exception as e:
                logger.error(f"Error copying saved PDF: {e}")
                pdf.save(output_path)  # Fallback to direct save
                return False
            finally:
                Path(temp_input).unlink()
                Path(temp_output).unlink()
        else:
            logger.warning(
                f"PDF save with clean=True failed with exit code {exit_code} or produced empty file"
            )
            # Fallback to save without clean parameter
            try:
                pdf.save(
                    output_path,
                    garbage=garbage,
                    deflate=deflate,
                    clean=False,
                    deflate_fonts=deflate_fonts,
                    linear=linear,
                )
            except Exception as e:
                logger.error(f"Error in fallback save: {e}")
                # Last resort: basic save
                pdf.save(output_path)

            return False

    def write(self, translation_config: TranslationConfig) -> TranslateResult:
        basename = Path(translation_config.input_file).stem
        debug_suffix = ".debug" if translation_config.debug else ""
        if translation_config.watermark_output_mode != WatermarkOutputMode.Watermarked:
            debug_suffix += ".no_watermark"
        mono_out_path = translation_config.get_output_file_path(
            f"{basename}{debug_suffix}.{translation_config.lang_out}.mono.pdf",
        )
        pdf = pymupdf.open(self.original_pdf_path)
        self.font_mapper.add_font(pdf, self.docs)
        with self.translation_config.progress_monitor.stage_start(
            self.stage_name,
            len(self.docs.page),
        ) as pbar:
            for page in self.docs.page:
                translation_config.raise_if_cancelled()
                xobj_available_fonts = {}
                xobj_draw_ops = {}
                xobj_encoding_length_map = {}
                available_font_list = self.get_available_font_list(pdf, page)

                for xobj in page.pdf_xobject:
                    xobj_available_fonts[xobj.xobj_id] = available_font_list.copy()
                    try:
                        xobj_available_fonts[xobj.xobj_id].update(
                            self.get_xobj_available_fonts(xobj.xref_id, pdf),
                        )
                    except Exception:
                        pass
                    xobj_encoding_length_map[xobj.xobj_id] = {
                        f.font_id: f.encoding_length for f in xobj.pdf_font
                    }
                    xobj_op = BitStream()
                    xobj_op.append(xobj.base_operations.value.encode())
                    xobj_draw_ops[xobj.xobj_id] = xobj_op
                page_encoding_length_map = {
                    f.font_id: f.encoding_length for f in page.pdf_font
                }
                page_op = BitStream()
                # q {ops_base}Q 1 0 0 1 {x0} {y0} cm {ops_new}
                page_op.append(b"q ")
                page_op.append(page.base_operations.value.encode())
                page_op.append(b" Q ")
                page_op.append(
                    f"q Q 1 0 0 1 {page.cropbox.box.x} {page.cropbox.box.y} cm \n".encode(),
                )
                # 收集所有字符
                chars = []
                # 首先添加页面级别的字符
                if page.pdf_character:
                    chars.extend(page.pdf_character)
                # 然后添加段落中的字符
                for paragraph in page.pdf_paragraph:
                    chars.extend(self.render_paragraph_to_char(paragraph))

                # 渲染所有字符
                for char in chars:
                    if char.char_unicode == "\n":
                        continue
                    if char.pdf_character_id is None:
                        # dummy char
                        continue
                    char_size = char.pdf_style.font_size
                    font_id = char.pdf_style.font_id
                    if char.xobj_id in xobj_available_fonts:
                        if font_id not in xobj_available_fonts[char.xobj_id]:
                            continue
                        draw_op = xobj_draw_ops[char.xobj_id]
                        encoding_length_map = xobj_encoding_length_map[char.xobj_id]
                    else:
                        if font_id not in available_font_list:
                            continue
                        draw_op = page_op
                        encoding_length_map = page_encoding_length_map

                    draw_op.append(b"q ")
                    self.render_graphic_state(draw_op, char.pdf_style.graphic_state)
                    if char.vertical:
                        draw_op.append(
                            f"BT /{font_id} {char_size:f} Tf 0 1 -1 0 {char.box.x2:f} {char.box.y:f} Tm ".encode(),
                        )
                    else:
                        draw_op.append(
                            f"BT /{font_id} {char_size:f} Tf 1 0 0 1 {char.box.x:f} {char.box.y:f} Tm ".encode(),
                        )

                    encoding_length = encoding_length_map[font_id]
                    # pdf32000-2008 page14:
                    # As hexadecimal data enclosed in angle brackets < >
                    # see 7.3.4.3, "Hexadecimal Strings."
                    draw_op.append(
                        f"<{char.pdf_character_id:0{encoding_length * 2}x}>".upper().encode(),
                    )

                    draw_op.append(b" Tj ET Q \n")
                for xobj in page.pdf_xobject:
                    draw_op = xobj_draw_ops[xobj.xobj_id]
                    pdf.update_stream(xobj.xref_id, draw_op.tobytes())
                    # pdf.update_stream(xobj.xref_id, b'')
                for rect in page.pdf_rectangle:
                    self._debug_render_rectangle(page_op, rect)
                draw_op = page_op
                op_container = pdf.get_new_xref()
                # Since this is a draw instruction container,
                # no additional information is needed
                pdf.update_object(op_container, "<<>>")
                pdf.update_stream(op_container, draw_op.tobytes())
                pdf[page.page_number].set_contents(op_container)
                pbar.advance()
        translation_config.raise_if_cancelled()
        with self.translation_config.progress_monitor.stage_start(
            SUBSET_FONT_STAGE_NAME,
            1,
        ) as pbar:
            if not translation_config.skip_clean:
                pdf = self.subset_fonts_in_subprocess(
                    pdf, translation_config, tag="mono"
                )

            pbar.advance()
        with self.translation_config.progress_monitor.stage_start(
            SAVE_PDF_STAGE_NAME,
            2,
        ) as pbar:
            if not translation_config.no_mono:
                if translation_config.debug:
                    translation_config.raise_if_cancelled()
                    pdf.save(
                        f"{mono_out_path}.decompressed.pdf",
                        expand=True,
                        pretty=True,
                    )
                translation_config.raise_if_cancelled()
                self.save_pdf_with_timeout(
                    pdf,
                    mono_out_path,
                    translation_config,
                    garbage=1,
                    deflate=True,
                    clean=not translation_config.skip_clean,
                    deflate_fonts=True,
                    linear=False,
                    tag="mono",
                )
            pbar.advance()
            dual_out_path = None
            if not translation_config.no_dual:
                dual_out_path = translation_config.get_output_file_path(
                    f"{basename}{debug_suffix}.{translation_config.lang_out}.dual.pdf",
                )
                translation_config.raise_if_cancelled()
                original_pdf = pymupdf.open(self.original_pdf_path)
                translated_pdf = pdf

                # Choose between alternating pages and side-by-side format
                # Default to side-by-side if not specified
                use_alternating_pages = translation_config.use_alternating_pages_dual

                if use_alternating_pages:
                    # Create a dual PDF with alternating pages (original and translation)
                    dual = self.create_alternating_pages_dual_pdf(
                        self.original_pdf_path,
                        translated_pdf,
                        translation_config,
                    )
                else:
                    # Create a dual PDF with side-by-side pages (original and translation)
                    dual = self.create_side_by_side_dual_pdf(
                        original_pdf,
                        translated_pdf,
                        dual_out_path,
                        translation_config,
                    )

                if translation_config.debug:
                    translation_config.raise_if_cancelled()
                    try:
                        dual = self.write_debug_info(dual, translation_config)
                    except Exception:
                        logger.warning(
                            "Failed to write debug info to dual PDF",
                            exc_info=True,
                        )

                self.save_pdf_with_timeout(
                    dual,
                    dual_out_path,
                    translation_config,
                    garbage=1,
                    deflate=True,
                    clean=not translation_config.skip_clean,
                    deflate_fonts=True,
                    linear=False,
                    tag="dual",
                )
                if translation_config.debug:
                    translation_config.raise_if_cancelled()
                    dual.save(
                        f"{dual_out_path}.decompressed.pdf",
                        expand=True,
                        pretty=True,
                    )
            pbar.advance()
        return TranslateResult(mono_out_path, dual_out_path)
