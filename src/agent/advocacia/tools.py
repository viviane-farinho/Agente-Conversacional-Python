"""
Ferramentas RAG para Advocacia

Este módulo contém as ferramentas LangChain para buscar informações
na base de conhecimento do RAG Advocacia.

Ferramentas disponíveis:
- buscar_documentos_advocacia: Busca documentos por área/serviço
- buscar_servicos_area: Lista serviços de uma área específica
- registrar_pergunta_sem_resposta: Registra perguntas não respondidas

Uso:
    from src.agent.advocacia.tools import get_advocacia_tools

    tools = get_advocacia_tools(area_ids=["previdenciario", "trabalhista"])
"""

from typing import List, Optional
from langchain_core.tools import tool

from src.services.rag_advocacia import (
    rag_advocacia_search_sync,
    rag_advocacia_list_servicos_sync,
    rag_advocacia_log_pergunta_sem_resposta
)


@tool
def buscar_documentos_advocacia(
    query: str,
    area_ids: Optional[List[str]] = None,
    servico_id: Optional[str] = None,
    limit: int = 5
) -> str:
    """
    Busca documentos na base de conhecimento jurídica.

    Use esta ferramenta para encontrar informações sobre:
    - Requisitos para benefícios/processos
    - Procedimentos legais
    - Direitos do cliente
    - Documentação necessária
    - Prazos e valores

    Args:
        query: Pergunta ou termo de busca
        area_ids: Lista de áreas do direito (ex: ["previdenciario", "trabalhista"])
        servico_id: ID do serviço específico (opcional)
        limit: Número máximo de resultados (default: 5)

    Returns:
        Documentos encontrados formatados
    """
    try:
        results = rag_advocacia_search_sync(
            query=query,
            area_ids=area_ids,
            servico_id=servico_id,
            agente="vendas",  # Documentos disponíveis para vendas
            limit=limit,
            similarity_threshold=0.3
        )

        if not results:
            return "Nenhum documento encontrado para essa consulta."

        # Formata resultados
        output = []
        for i, doc in enumerate(results, 1):
            output.append(f"[{i}] {doc['titulo']}")
            if doc.get('categoria'):
                output.append(f"    Categoria: {doc['categoria']}")
            output.append(f"    {doc['conteudo'][:500]}...")
            output.append("")

        return "\n".join(output)

    except Exception as e:
        return f"Erro ao buscar documentos: {str(e)}"


@tool
def buscar_servicos_area(area_id: str) -> str:
    """
    Lista os serviços disponíveis em uma área do direito.

    Use esta ferramenta para:
    - Mostrar opções de serviço ao cliente
    - Entender o que o escritório oferece na área
    - Qualificar o lead para o serviço correto

    Args:
        area_id: ID da área (ex: "previdenciario", "trabalhista")

    Returns:
        Lista de serviços da área
    """
    try:
        servicos = rag_advocacia_list_servicos_sync(area_id=area_id)

        if not servicos:
            return f"Nenhum serviço cadastrado para a área '{area_id}'."

        output = [f"Serviços disponíveis em {area_id}:\n"]
        for servico in servicos:
            output.append(f"- {servico['nome']}")
            if servico.get('descricao'):
                output.append(f"  {servico['descricao']}")

        return "\n".join(output)

    except Exception as e:
        return f"Erro ao buscar serviços: {str(e)}"


@tool
def buscar_informacoes_gerais(query: str, limit: int = 5) -> str:
    """
    Busca informações gerais sobre o escritório (sem filtro de área).

    Use esta ferramenta para:
    - Informações sobre o escritório
    - Horários de funcionamento
    - Localização e contato
    - Formas de pagamento
    - Dúvidas gerais

    Args:
        query: Pergunta ou termo de busca
        limit: Número máximo de resultados

    Returns:
        Informações encontradas
    """
    try:
        # Busca documentos marcados para suporte (agente=suporte ou agente=NULL)
        results = rag_advocacia_search_sync(
            query=query,
            area_ids=None,  # Sem filtro de área
            servico_id=None,
            agente="suporte",
            limit=limit,
            similarity_threshold=0.3
        )

        if not results:
            return "Nenhuma informação encontrada para essa consulta."

        output = []
        for i, doc in enumerate(results, 1):
            output.append(f"[{i}] {doc['titulo']}")
            output.append(f"    {doc['conteudo'][:500]}...")
            output.append("")

        return "\n".join(output)

    except Exception as e:
        return f"Erro ao buscar informações: {str(e)}"


# ============================================================================
# Funções para criar ferramentas com contexto
# ============================================================================

def get_vendas_tools(area_ids: Optional[List[str]] = None) -> list:
    """
    Retorna ferramentas para o agente de vendas.

    Args:
        area_ids: Áreas detectadas para filtrar busca

    Returns:
        Lista de ferramentas LangChain
    """
    # Cria ferramenta de busca com área pré-configurada
    @tool
    def buscar_documentos(query: str, limit: int = 5) -> str:
        """
        Busca documentos na base de conhecimento jurídica.

        Use para encontrar:
        - Requisitos para benefícios/processos
        - Procedimentos e prazos
        - Direitos do cliente
        - Documentação necessária

        Args:
            query: Pergunta ou termo de busca
            limit: Número máximo de resultados (default: 5)

        Returns:
            Documentos encontrados
        """
        return buscar_documentos_advocacia.invoke({
            "query": query,
            "area_ids": area_ids,
            "limit": limit
        })

    @tool
    def listar_servicos() -> str:
        """
        Lista os serviços disponíveis nas áreas identificadas.

        Use para mostrar ao cliente os serviços que o escritório oferece.

        Returns:
            Lista de serviços por área
        """
        if not area_ids:
            return "Nenhuma área identificada. Pergunte ao cliente sobre qual situação ele precisa de ajuda."

        output = []
        for area_id in area_ids:
            result = buscar_servicos_area.invoke({"area_id": area_id})
            output.append(result)

        return "\n\n".join(output)

    return [buscar_documentos, listar_servicos]


def get_suporte_tools() -> list:
    """
    Retorna ferramentas para o agente de suporte.

    Returns:
        Lista de ferramentas LangChain
    """
    return [buscar_informacoes_gerais]


def get_agendamento_tools() -> list:
    """
    Retorna ferramentas para o agente de agendamento.

    Returns:
        Lista de ferramentas LangChain (vazio por enquanto)
    """
    # Agendamento não precisa de RAG por enquanto
    # Pode adicionar ferramenta para verificar horários disponíveis no futuro
    return []


# ============================================================================
# Função auxiliar para registrar perguntas sem resposta
# ============================================================================

async def registrar_pergunta_nao_respondida(
    pergunta: str,
    area_id: Optional[str] = None,
    agente: str = "vendas",
    telefone: Optional[str] = None
) -> bool:
    """
    Registra uma pergunta que não foi respondida.

    Args:
        pergunta: Texto da pergunta
        area_id: Área do direito relacionada
        agente: Agente que não conseguiu responder
        telefone: Telefone do cliente (se disponível)

    Returns:
        True se registrou com sucesso
    """
    try:
        await rag_advocacia_log_pergunta_sem_resposta(
            pergunta=pergunta,
            area_id=area_id,
            agente=agente,
            telefone=telefone
        )
        return True
    except Exception as e:
        print(f"[Tools] Erro ao registrar pergunta: {e}")
        return False
