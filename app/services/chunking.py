import re
from typing import Callable

from llama_index.core.node_parser import (
    SentenceSplitter,
    SemanticSplitterNodeParser,
    TokenTextSplitter,
)
from llama_index.core.node_parser.interface import NodeParser
from llama_index.core.embeddings import BaseEmbedding


def russian_sentence_tokenizer(text: str) -> list[str]:
    """
    Простой tokenizer для разбиения русского текста на предложения.

    SentenceSplitter умеет работать с пользовательской функцией разбиения.
    Нам важно, чтобы текст делился не только по английским правилам,
    но и нормально обрабатывал русские предложения.
    """

    if not text:
        return []

    # Разбиваем текст после точки, вопросительного знака, восклицательного знака
    # или многоточия, если дальше идёт пробел.
    sentences = re.split(r"(?<=[.!?…])\s+", text.strip())

    # Убираем пустые строки, если они вдруг появились.
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def fixed_size(
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> NodeParser:
    """
    Baseline-стратегия chunking.

    Режет текст по токенам без учёта границ предложений.
    Используется как простая базовая стратегия для сравнения.
    """

    return TokenTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


def recursive(
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    paragraph_separator: str = "\n\n",
    chunking_tokenizer_fn: Callable[[str], list[str]] = russian_sentence_tokenizer,
) -> NodeParser:
    """
    Recursive-подход через SentenceSplitter.

    В задании указано использовать SentenceSplitter с paragraph_separator="\\n\\n"
    и chunking_tokenizer_fn под русские предложения.

    Это не HierarchicalNodeParser.
    """

    return SentenceSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        paragraph_separator=paragraph_separator,
        chunking_tokenizer_fn=chunking_tokenizer_fn,
    )


def semantic(
    embed_model: BaseEmbedding,
    buffer_size: int = 1,
    breakpoint_percentile_threshold: int = 95,
) -> NodeParser:
    """
    Semantic chunking.

    Делит текст не просто по размеру, а по смысловым разрывам.
    Для работы использует ту же embedding-модель, что и индекс.
    """

    return SemanticSplitterNodeParser(
        buffer_size=buffer_size,
        breakpoint_percentile_threshold=breakpoint_percentile_threshold,
        embed_model=embed_model,
    )