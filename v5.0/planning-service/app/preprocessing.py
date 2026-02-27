import time
from typing import Callable, Dict, Generator, List, Sequence, TypeVar

from app.config import settings


T = TypeVar("T")


def chunk_generator(items: Sequence[T], chunk_size: int) -> Generator[List[T], None, None]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than 0")
    for start in range(0, len(items), chunk_size):
        yield list(items[start : start + chunk_size])


def compute_chunk_sizes(total_points: int, chunk_size: int) -> List[int]:
    if total_points <= 0:
        return []
    full_chunks, remainder = divmod(total_points, chunk_size)
    sizes = [chunk_size] * full_chunks
    if remainder:
        sizes.append(remainder)
    return sizes


def mock_chunk_processor(chunk: Sequence[T], chunk_index: int) -> Dict:
    """
    Placeholder processor for future routing integration.
    """
    time.sleep(settings.mock_chunk_delay_seconds)
    return {
        "chunk_index": chunk_index,
        "processed_points": len(chunk),
        "status": "ok",
    }


_chunk_processor: Callable[[Sequence[T], int], Dict] = mock_chunk_processor


def set_chunk_processor(processor: Callable[[Sequence[T], int], Dict]) -> None:
    """
    Allows future routing engine injection without changing endpoint code.
    """
    global _chunk_processor
    _chunk_processor = processor


def get_chunk_processor() -> Callable[[Sequence[T], int], Dict]:
    return _chunk_processor


def process_chunks(
    items: Sequence[T],
    chunk_size: int,
    processor: Callable[[Sequence[T], int], Dict] | None = None,
) -> List[Dict]:
    if processor is None:
        processor = _chunk_processor
    results: List[Dict] = []
    for idx, chunk in enumerate(chunk_generator(items, chunk_size)):
        results.append(processor(chunk, idx))
    return results
