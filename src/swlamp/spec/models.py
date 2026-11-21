"""Lamp spec: a template (shared design) plus an order (named parameter values).

All lengths are millimetres. A part is a box: a rectangular base with zero to four
walls bent up along its edges. A box with no walls is a flat panel. Dimensions are
outside (mould-line) dimensions of the folded part.

Face-local coordinates used by holes, patterns, text, artwork and slots:

* ``base``: origin at the base centre, ``x`` towards the right wall, ``y`` towards the back wall.
* a wall (``front``, ``back``, ``left``, ``right``) seen from outside the box: ``x`` runs along
  the wall (origin at its middle, increasing to the viewer's right), ``y`` is the height above
  the outside bottom face of the box.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Side = Literal["front", "back", "left", "right"]
FaceName = Literal["base", "front", "back", "left", "right"]
Material = Literal["stainless", "steel", "aluminium"]
SIDES: tuple[Side, ...] = ("front", "back", "left", "right")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Hem(_Model):
    length: float = Field(gt=0, description="Folded length of the hem return")
    kind: Literal["open", "closed"] = "open"


class Wall(_Model):
    height: float = Field(gt=0)
    lip: float | None = Field(default=None, gt=0, description="Return flange folded inward")
    hem: Hem | None = None


class Hole(_Model):
    face: FaceName = "base"
    x: float = 0.0
    y: float = 0.0
    d: float = Field(gt=0)


class Pattern(_Model):
    face: FaceName = "base"
    kind: Literal["grid", "hex"] = "hex"
    size: float = Field(gt=0, description="Hole diameter (grid) or hexagon across-flats (hex)")
    web: float = Field(gt=0, description="Material left between neighbouring holes")
    margin: float = Field(default=5.0, ge=0, description="Clear band inside the usable face")


class Text(_Model):
    face: FaceName = "front"
    text: str
    height: float = Field(gt=0, description="Cap height")
    x: float = 0.0
    y: float = 0.0
    font: str | None = Field(default=None, description="Path to a TTF/OTF font")

    @field_validator("text", mode="before")
    @classmethod
    def _numbers_are_text(cls, v):
        return str(v) if isinstance(v, (int, float)) else v


class Artwork(_Model):
    face: FaceName = "base"
    file: str
    width: float = Field(gt=0)
    x: float = 0.0
    y: float = 0.0


class Tabs(_Model):
    """Straight tabs standing up from a wall's top edge, to pass through slots in a panel."""

    wall: Side
    at: list[float] = Field(min_length=1, description="Tab centres along the wall (face x)")
    width: float = Field(gt=0)
    length: float | None = Field(default=None, gt=0, description="Default: mating T + 2 mm")
    mating_thickness: float | None = Field(default=None, gt=0, description="Default: own T")

    def effective_length(self, thickness: float) -> float:
        return self.length or (self.mating_thickness or thickness) + 2


class Slot(_Model):
    face: FaceName = "base"
    x: float = 0.0
    y: float = 0.0
    tab_width: float = Field(gt=0)
    tab_thickness: float | None = Field(default=None, gt=0, description="Default: own T")
    angle: Literal[0, 90] = 0

    def effective_thickness(self, thickness: float) -> float:
        return self.tab_thickness or thickness


class Part(_Model):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    width: float = Field(gt=0)
    depth: float = Field(gt=0)
    walls: dict[Side, Wall] = Field(default_factory=dict)
    holes: list[Hole] = Field(default_factory=list)
    patterns: list[Pattern] = Field(default_factory=list)
    texts: list[Text] = Field(default_factory=list)
    artworks: list[Artwork] = Field(default_factory=list)
    tabs: list[Tabs] = Field(default_factory=list)
    slots: list[Slot] = Field(default_factory=list)


class PrintedPart(_Model):
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(description="Path to the user's parametric .SLDPRT")
    vars: dict[str, float] = Field(default_factory=dict)

    @field_validator("vars")
    @classmethod
    def _only_order_vars(cls, v: dict[str, float]) -> dict[str, float]:
        bad = [k for k in v if not k.startswith("ord_")]
        if bad:
            raise ValueError(
                f"Chỉ được đổi biến có tiền tố 'ord_'; không được đổi: {', '.join(bad)}"
            )
        return v


class Lamp(_Model):
    """A fully resolved spec: template with the order's parameters substituted."""

    name: str
    material: Material
    thickness: float = Field(gt=0)
    shop: str = "default"
    die_v: float | None = Field(default=None, gt=0, description="Press-brake die opening (mm)")
    coat_um: float = Field(default=80.0, ge=0, description="Powder coat per side (µm)")
    parts: list[Part] = Field(min_length=1)
    printed_parts: list[PrintedPart] = Field(default_factory=list)


class Order(_Model):
    order_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    params: dict[str, float | int | str] = Field(default_factory=dict)
