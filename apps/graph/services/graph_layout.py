from typing import Protocol


class GraphLayoutProvider(Protocol):
    def layout(self, points: list) -> dict[str, tuple[float, float]]: ...


class ChapterLayout:
    """Deterministic four-column layout, independent of the student's progress."""
    def layout(self, points):
        positions = {"course": (700, 50)}
        for chapter in range(1, 5):
            positions[f"chapter_{chapter:02d}"] = (175 + (chapter - 1) * 350, 150)
            in_chapter = sorted([point for point in points if point.chapter == chapter], key=lambda p: (p.order, p.slug))
            for row, point in enumerate(in_chapter):
                positions[point.slug] = (175 + (chapter - 1) * 350, 250 + row * 80)
        return positions
