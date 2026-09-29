"""Helpers for selecting Docling layout models."""

from __future__ import annotations


def resolve_docling_layout_model(model_name: str):
    from docling.datamodel.layout_model_specs import (
        DOCLING_LAYOUT_EGRET_LARGE,
        DOCLING_LAYOUT_EGRET_MEDIUM,
        DOCLING_LAYOUT_EGRET_XLARGE,
        DOCLING_LAYOUT_HERON,
        DOCLING_LAYOUT_HERON_101,
        DOCLING_LAYOUT_V2,
    )

    normalized = (model_name or "docling_layout_heron").strip().lower().replace("-", "_")
    supported = {
        "docling_layout_heron": DOCLING_LAYOUT_HERON,
        "docling_layout_heron_101": DOCLING_LAYOUT_HERON_101,
        "docling_layout_egret_medium": DOCLING_LAYOUT_EGRET_MEDIUM,
        "docling_layout_egret_large": DOCLING_LAYOUT_EGRET_LARGE,
        "docling_layout_egret_xlarge": DOCLING_LAYOUT_EGRET_XLARGE,
        "docling_layout_v2": DOCLING_LAYOUT_V2,
    }

    if normalized not in supported:
        raise ValueError(
            "Unsupported Docling layout model. Supported values are: "
            "docling_layout_heron, docling_layout_heron_101, docling_layout_egret_medium, "
            "docling_layout_egret_large, docling_layout_egret_xlarge, docling_layout_v2."
        )

    return supported[normalized]
