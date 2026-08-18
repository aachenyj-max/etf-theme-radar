from __future__ import annotations

from pathlib import Path
from io import BytesIO

import pytest

from etf_theme_radar.knowledge_base import KnowledgeBase
from etf_theme_radar.store import EvidenceStore


NOW = "2026-08-18T00:00:00+00:00"


def _library(tmp_path: Path) -> tuple[EvidenceStore, KnowledgeBase]:
    store = EvidenceStore(tmp_path / "knowledge.db")
    return store, KnowledgeBase(store, files_root=tmp_path / "knowledge-files")


def test_item_versions_use_hashes_and_controlled_paths(tmp_path: Path) -> None:
    store, library = _library(tmp_path)
    try:
        created = library.create_item(
            item_id="knowledge-1",
            owner_user_id="user-a",
            kind="meeting_material",
            title="机器人供应商会议",
            content=b"first version",
            filename="meeting.txt",
            mime_type="text/plain",
            theme_id="robotics",
            folder_id="folder-a",
            created_at=NOW,
        )
        replaced = library.replace_content(
            item_id="knowledge-1",
            owner_user_id="user-a",
            content=b"second version",
            filename="meeting.txt",
            mime_type="text/plain",
            created_at="2026-08-18T00:01:00+00:00",
        )

        assert created["current_version"] == 1
        assert created["content_hash"] != ""
        assert replaced["current_version"] == 2
        assert replaced["content_hash"] != created["content_hash"]
        assert "/" in replaced["storage_path"]
        assert ".." not in replaced["storage_path"]
        assert (tmp_path / "knowledge-files" / replaced["storage_path"]).read_bytes() == b"second version"
        assert [item["version"] for item in library.versions("knowledge-1", "user-a")] == [1, 2]
    finally:
        store.close()


def test_item_rejects_paths_outside_the_controlled_directory(tmp_path: Path) -> None:
    store, library = _library(tmp_path)
    try:
        with pytest.raises(ValueError, match="filename"):
            library.create_item(
                item_id="knowledge-escape",
                owner_user_id="user-a",
                kind="upload",
                title="escape",
                content=b"x",
                filename="..\\escape.txt",
                mime_type="text/plain",
                theme_id="",
                folder_id="folder-a",
                created_at=NOW,
            )
    finally:
        store.close()


def test_soft_delete_restores_without_rewriting_old_versions(tmp_path: Path) -> None:
    store, library = _library(tmp_path)
    try:
        library.create_item(
            item_id="knowledge-restore",
            owner_user_id="user-a",
            kind="note",
            title="私有笔记",
            content=b"preserve this",
            filename="note.md",
            mime_type="text/markdown",
            theme_id="robotics",
            folder_id="folder-a",
            created_at=NOW,
        )
        deleted = library.soft_delete("knowledge-restore", "user-a", deleted_at=NOW)
        restored = library.restore("knowledge-restore", "user-a", restored_at="2026-08-18T00:02:00+00:00")

        assert deleted["status"] == "deleted"
        assert restored["status"] == "active"
        assert restored["current_version"] == 1
        assert library.read_content("knowledge-restore", "user-a") == b"preserve this"
        assert [item["version"] for item in library.versions("knowledge-restore", "user-a")] == [1]
    finally:
        store.close()


def test_missing_version_file_is_not_returned_as_content(tmp_path: Path) -> None:
    store, library = _library(tmp_path)
    try:
        created = library.create_item(
            item_id="knowledge-missing",
            owner_user_id="user-a",
            kind="upload",
            title="待核验文件",
            content=b"original",
            filename="original.txt",
            mime_type="text/plain",
            theme_id="",
            folder_id="folder-a",
            created_at=NOW,
        )
        (tmp_path / "knowledge-files" / created["storage_path"]).unlink()

        item = library.item("knowledge-missing", "user-a")
        assert item is not None
        assert item["status"] == "missing_file"
        assert library.read_content("knowledge-missing", "user-a") is None
    finally:
        store.close()


def test_parser_chunks_a_frozen_version_with_page_and_character_locations(tmp_path: Path) -> None:
    store, library = _library(tmp_path)
    try:
        library.create_item(
            item_id="knowledge-parse",
            owner_user_id="user-a",
            kind="meeting_material",
            title="两页会议材料",
            content="第一页的机器人硬件。\f第二页的供应商信息。".encode(),
            filename="meeting.txt",
            mime_type="text/plain",
            theme_id="robotics",
            folder_id="folder-a",
            created_at=NOW,
        )

        chunks = library.parse_current_version("knowledge-parse", "user-a", chunk_size=6, overlap=2)

        assert [chunk["page_number"] for chunk in chunks] == [1, 1, 2, 2]
        assert all(chunk["char_end"] > chunk["char_start"] for chunk in chunks)
        assert {chunk["source_type"] for chunk in chunks} == {"meeting_material"}
        assert [chunk["version"] for chunk in chunks] == [1, 1, 1, 1]
        assert store.conn.execute(
            "SELECT COUNT(*) FROM document_chunks WHERE knowledge_item_id='knowledge-parse' AND version=1"
        ).fetchone()[0] == 4
    finally:
        store.close()


def test_parser_extracts_pdf_pages_and_docx_character_positions(tmp_path: Path) -> None:
    from docx import Document
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    document = Document()
    document.add_paragraph("DOCX 内部机器人材料")
    docx_bytes = BytesIO()
    document.save(docx_bytes)

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(DictionaryObject({
                NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })),
        }),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (PDF hardware material) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    pdf_bytes = BytesIO()
    writer.write(pdf_bytes)

    store, library = _library(tmp_path)
    try:
        for item_id, content, filename, mime_type in (
            ("knowledge-pdf", pdf_bytes.getvalue(), "material.pdf", "application/pdf"),
            ("knowledge-docx", docx_bytes.getvalue(), "material.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ):
            library.create_item(
                item_id=item_id, owner_user_id="user-a", kind="upload", title=item_id,
                content=content, filename=filename, mime_type=mime_type, theme_id="robotics",
                folder_id="folder-a", created_at=NOW,
            )
        pdf_chunks = library.parse_current_version("knowledge-pdf", "user-a", chunk_size=100, overlap=0)
        docx_chunks = library.parse_current_version("knowledge-docx", "user-a", chunk_size=100, overlap=0)

        assert pdf_chunks[0]["page_number"] == 1
        assert "PDF hardware material" in pdf_chunks[0]["text"]
        assert docx_chunks[0]["page_number"] is None
        assert docx_chunks[0]["char_end"] > docx_chunks[0]["char_start"]
    finally:
        store.close()
