"""OCR MCP Server - 基于 RapidOCR 的图片文字识别服务"""

from mcp.server.fastmcp import FastMCP
from rapidocr_onnxruntime import RapidOCR
from pathlib import Path

mcp = FastMCP("ocr")
ocr = RapidOCR()


@mcp.tool()
def read_image(image_path: str) -> str:
    """读取图片中的文字内容（OCR）。支持中英文。传入图片的绝对路径，返回识别出的文字。"""
    path = Path(image_path)
    if not path.exists():
        return f"错误：文件不存在 - {image_path}"
    if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}:
        return f"错误：不支持的图片格式 - {path.suffix}"

    result, _ = ocr(str(path))
    if not result:
        return "图片中未识别到文字"

    lines = [item[1] for item in result]
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
