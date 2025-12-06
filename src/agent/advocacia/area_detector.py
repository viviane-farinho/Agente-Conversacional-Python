"""
Detector de Áreas do Direito para Advocacia

Este módulo detecta a área do direito com base na mensagem do usuário.

Processo:
1. Busca keywords de cada área no banco de dados
2. Verifica se alguma keyword aparece na mensagem
3. Se não encontrar por keywords, usa LLM como fallback
4. Retorna no máximo 3 áreas (as mais relevantes)

Uso:
    from src.agent.advocacia.area_detector import detect_areas

    # Detecção por keywords (síncrono)
    areas = detect_areas_by_keywords("Quero me aposentar por invalidez")
    # Retorna: ["previdenciario"]

    # Detecção completa com LLM fallback (assíncrono)
    areas = await detect_areas("Meu patrão não pagou minhas horas extras")
    # Retorna: ["trabalhista"]
"""

import re
from typing import List, Optional
from langchain_openai import ChatOpenAI

from src.services.rag_advocacia import (
    rag_advocacia_get_keywords_por_area_sync,
    rag_advocacia_list_areas
)
from src.config import Config


# Cache das keywords por área
_keywords_cache: Optional[dict] = None
_areas_cache: Optional[List[dict]] = None

# Máximo de áreas a retornar
MAX_AREAS = 3


def _normalize_text(text: str) -> str:
    """Normaliza texto para comparação (lowercase, sem acentos)"""
    # Lowercase
    text = text.lower()

    # Remove acentos comuns
    replacements = {
        'á': 'a', 'à': 'a', 'ã': 'a', 'â': 'a',
        'é': 'e', 'ê': 'e',
        'í': 'i',
        'ó': 'o', 'ô': 'o', 'õ': 'o',
        'ú': 'u', 'ü': 'u',
        'ç': 'c'
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def _get_keywords_cache() -> dict:
    """Retorna cache de keywords (carrega do banco se necessário)"""
    global _keywords_cache
    if _keywords_cache is None:
        _keywords_cache = rag_advocacia_get_keywords_por_area_sync()
    return _keywords_cache


def clear_keywords_cache():
    """Limpa cache de keywords (chamar após atualizar áreas)"""
    global _keywords_cache, _areas_cache
    _keywords_cache = None
    _areas_cache = None


def detect_areas_by_keywords(text: str) -> List[str]:
    """
    Detecta áreas do direito por keywords na mensagem.

    Args:
        text: Texto da mensagem do usuário

    Returns:
        Lista de area_ids encontradas (máximo MAX_AREAS)
    """
    keywords_por_area = _get_keywords_cache()

    if not keywords_por_area:
        return []

    # Normaliza texto de entrada
    normalized_text = _normalize_text(text)

    # Conta matches por área
    area_scores: dict = {}

    for area_id, keywords in keywords_por_area.items():
        score = 0
        for keyword in keywords:
            # Normaliza keyword
            normalized_keyword = _normalize_text(keyword)

            # Verifica se keyword aparece no texto (word boundary)
            # Usa regex para match de palavra inteira
            pattern = r'\b' + re.escape(normalized_keyword) + r'\b'
            matches = re.findall(pattern, normalized_text)
            score += len(matches)

        if score > 0:
            area_scores[area_id] = score

    # Ordena por score e retorna top MAX_AREAS
    sorted_areas = sorted(area_scores.items(), key=lambda x: x[1], reverse=True)
    return [area_id for area_id, _ in sorted_areas[:MAX_AREAS]]


async def detect_areas_by_llm(text: str, areas_disponiveis: List[dict]) -> List[str]:
    """
    Detecta áreas do direito usando LLM (fallback).

    Args:
        text: Texto da mensagem do usuário
        areas_disponiveis: Lista de áreas disponíveis com id, nome e descrição

    Returns:
        Lista de area_ids detectadas pelo LLM (máximo MAX_AREAS)
    """
    if not areas_disponiveis:
        return []

    # Monta lista de áreas para o prompt
    areas_str = "\n".join([
        f"- {a['id']}: {a['nome']} - {a.get('descricao', '')}"
        for a in areas_disponiveis
    ])

    prompt = f"""Você é um classificador de áreas do direito.

ÁREAS DISPONÍVEIS:
{areas_str}

MENSAGEM DO USUÁRIO:
"{text}"

TAREFA:
Identifique qual(is) área(s) do direito a mensagem se refere.
Retorne APENAS os IDs das áreas, separados por vírgula.
Se a mensagem não se enquadrar em nenhuma área específica, retorne "nenhuma".
Máximo de {MAX_AREAS} áreas.

RESPOSTA (apenas IDs separados por vírgula):"""

    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",  # Modelo rápido e barato para classificação
            temperature=0,
            api_key=Config.OPENAI_API_KEY
        )

        response = await llm.ainvoke(prompt)
        result = response.content.strip().lower()

        if result == "nenhuma" or not result:
            return []

        # Parse resultado
        area_ids = [aid.strip() for aid in result.split(",")]

        # Valida que são áreas válidas
        valid_area_ids = {a["id"] for a in areas_disponiveis}
        detected = [aid for aid in area_ids if aid in valid_area_ids]

        return detected[:MAX_AREAS]

    except Exception as e:
        print(f"[AreaDetector] Erro no LLM fallback: {e}")
        return []


async def detect_areas(text: str, use_llm_fallback: bool = True) -> List[str]:
    """
    Detecta áreas do direito na mensagem (keywords + LLM fallback).

    Args:
        text: Texto da mensagem do usuário
        use_llm_fallback: Se True, usa LLM quando keywords não encontram nada

    Returns:
        Lista de area_ids (máximo MAX_AREAS)
    """
    # 1. Tenta por keywords primeiro (rápido e sem custo)
    areas_by_keywords = detect_areas_by_keywords(text)

    if areas_by_keywords:
        return areas_by_keywords

    # 2. Se não encontrou por keywords e LLM fallback está habilitado
    if use_llm_fallback:
        # Carrega áreas do banco para o LLM
        areas_disponiveis = await rag_advocacia_list_areas()
        if areas_disponiveis:
            return await detect_areas_by_llm(text, areas_disponiveis)

    return []


def detect_areas_sync(text: str) -> List[str]:
    """
    Versão síncrona da detecção (apenas keywords, sem LLM).

    Args:
        text: Texto da mensagem do usuário

    Returns:
        Lista de area_ids
    """
    return detect_areas_by_keywords(text)


# ============================================================================
# Funções auxiliares para testes
# ============================================================================

def get_all_keywords() -> dict:
    """Retorna todas as keywords por área (para debug)"""
    return _get_keywords_cache()


async def test_detection(text: str) -> dict:
    """
    Testa detecção de área e retorna detalhes.

    Args:
        text: Texto para testar

    Returns:
        Dict com resultados da detecção
    """
    # Por keywords
    keywords_result = detect_areas_by_keywords(text)

    # Por LLM
    areas_disponiveis = await rag_advocacia_list_areas()
    llm_result = await detect_areas_by_llm(text, areas_disponiveis) if areas_disponiveis else []

    # Detecção completa
    final_result = await detect_areas(text)

    return {
        "texto": text,
        "por_keywords": keywords_result,
        "por_llm": llm_result,
        "resultado_final": final_result,
        "metodo_usado": "keywords" if keywords_result else ("llm" if llm_result else "nenhum")
    }
