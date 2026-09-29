from __future__ import annotations

import json
from typing import List
from typing import Literal

from pydantic import BaseModel, Field


class TableRow(BaseModel):
    cells: List[str] = Field(default_factory=list, description="Cell values from left to right")


class Table(BaseModel):
    title: str = Field(default="", description="Short table name")
    type_detected: str = Field(default="", description="Precise table type, for example simple table, financial table, invoice table, comparison table, schedule table, summary table, employee table, pivot table, form table, nested table or matrix table")
    description: str = Field(default="", description="One sentence describing what the table contains")
    row_count: int = Field(default=0, description="Number of rows")
    column_count: int = Field(default=0, description="Number of columns")
    columns: List[str] = Field(default_factory=list, description="Column headers from left to right")
    rows: List[TableRow] = Field(default_factory=list, description="Table rows")


class ChartDataPoint(BaseModel):
    label: str = Field(description="Visible chart label, category, month, task name or item name, without connectors or decorative symbols")
    value: str = Field(description="Visible information linked to the label, exactly as shown; it may be a number, text, date, range, status, or value with unit, without connectors such as >, <, /, arrows, lines or bullets")


class Chart(BaseModel):
    title: str = Field(default="", description="Visible or inferred chart title")
    type_detected: str = Field(default="", description="Precise chart type, for example bar chart, column chart, line chart, pie chart, donut chart, area chart, stacked bar chart, grouped bar chart, scatter plot, bubble chart, radar chart, heatmap, waterfall chart, funnel chart, gauge chart, treemap, box plot, candlestick chart, histogram, Gantt chart or Excel chart")
    description: str = Field(default="", description="Short summary of what the chart represents")
    data_points: List[ChartDataPoint] = Field(default_factory=list, description="All visible chart label-value pairs, including small, external, left-side, right-side, top or bottom labels")
    interpretation: str = Field(default="", description="Short interpretation of the chart")


class DiagramElement(BaseModel):
    name: str = Field(default="", description="Visible element name or label")
    role: str = Field(default="", description="Element role, for example task, step, component, node, decision, service, database, stateactor, use case, class or entity")


class DiagramRelation(BaseModel):
    source: str = Field(default="", description="Source element")
    target: str = Field(default="", description="Target element")
    relation_type: str = Field(default="", description="Relation type, for example include, extend, association, arrow, dependency, hierarchy, sequence, data flow, connection, transition or flow")
    description: str = Field(default="", description="Short explanation of the relation")


class Diagram(BaseModel):
    title: str = Field(default="", description="Visible or inferred diagram title")
    type_detected: str = Field(default="", description="Precise diagram type, for example UML use case diagram, class diagram, sequence diagram, workflow diagram, flowchart, process diagram, block diagram, architecture diagram, system diagram, component diagram, deployment diagram, network diagram, pipeline diagram, data flow diagram, entity relationship diagram, activity diagram, state diagram, decision tree, mind map, concept map, fishbone diagram, Venn diagram, timeline, organizational chart, matrix diagram, SWOT matrix or technical drawing")
    description: str = Field(default="", description="One sentence describing what the diagram represents")
    elements: List[DiagramElement] = Field(default_factory=list, description="Main visible elements inside the diagram")
    relations: List[DiagramRelation] = Field(default_factory=list, description="Visible links, arrows, include relations, dependencies, associations, hierarchy relations, sequences or flows")
    interpretation: str = Field(default="", description="Short interpretation of the diagram")


class VisualObject(BaseModel):
    type_detected: Literal["logo", "brand_mark", "stamp", "signature", "signature_block", "qr_code", "barcode", "checkbox", "radio_button", "photo", "icon", "watermark", "seal", "handwritten_mark", "highlight"] = Field(description="Detected non-text visual object only. Never use text, table, chart, graph or diagram here.")
    description: str = Field(default="", description="Short description of the visual object only, not normal OCR text.")
    visible_text: str = Field(default="", description="Text inside or directly attached to the visual object only, for example logo text, stamp text or signature label. Do not copy normal document text.")
    state: str = Field(default="", description="State if applicable: checked, unchecked, signed, stamped, faded, selected, unclear or partially visible.")


class OCRResult(BaseModel):
    summary: str = Field(default="", description="Short summary of important visual or structural content not fully represented by Markdown")
    visual_objects: List[VisualObject] = Field(default_factory=list, description="Detected non-text visual objects only when visible, such as logos, stamps, signatures, QR codes, barcodes, checkboxes, photos, icons, seals, watermarks or handwritten marks. Do not include charts, graphs, tables or diagrams here")
    tables: List[Table] = Field(default_factory=list, description="Detected tables only when tables are visible")
    charts: List[Chart] = Field(default_factory=list, description="Detected charts and graphs only when visible. Include bar charts, line charts, pie charts, Gantt charts, histograms, area charts, scatter plots, Excel charts and other measurable graphs. Put numeric or period values in data_points")
    diagrams: List[Diagram] = Field(default_factory=list, description="Detected diagrams only when visible. Include UML diagrams, workflows, flowcharts, architecture schemas, data flow diagrams, process diagrams, timelines, maps, organizational charts and technical drawings. Put elements and relations here")


schema_input = json.dumps(OCRResult.model_json_schema(), ensure_ascii=False)
