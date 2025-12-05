"""
Ferramentas de Agenda para o Agente
Usa conexao sincrona (psycopg2) para evitar problemas com asyncio em threads
"""
from typing import Optional, Annotated
from langchain_core.tools import tool
from datetime import datetime, date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

from src.config import Config


def _get_connection():
    """Retorna uma conexao sincrona com o banco"""
    conn_string = Config.DATABASE_URL
    if not conn_string:
        conn_string = f"postgresql://{Config.POSTGRES_USER}:{Config.POSTGRES_PASSWORD}@{Config.POSTGRES_HOST}:{Config.POSTGRES_PORT}/{Config.POSTGRES_DB}"
    return psycopg2.connect(conn_string)


def _get_business_type_sync():
    """Obtem o business_type da configuracao do sistema (sincrono)"""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT value FROM system_config WHERE key = 'business_type'
            """)
            row = cur.fetchone()
            return row["value"] if row else "clinica"
    finally:
        conn.close()


def _listar_profissionais_sync(business_type: str = None):
    """Lista profissionais (sincrono)"""
    conn = _get_connection()
    try:
        # Se nao foi passado business_type, pega da configuracao
        if business_type is None:
            business_type = _get_business_type_sync()

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT id, nome, especialidade, cargo, business_type, ativo
                FROM profissionais
                WHERE ativo = true AND business_type = %s
                ORDER BY nome
            """, (business_type,))
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _buscar_agendamentos_sync(profissional_id=None, data_inicio=None, data_fim=None, telefone=None):
    """Busca agendamentos (sincrono)"""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            query = """
                SELECT a.*, p.nome as profissional_nome, p.especialidade
                FROM agendamentos a
                JOIN profissionais p ON a.profissional_id = p.id
                WHERE a.status != 'cancelado'
            """
            params = []

            if profissional_id:
                query += " AND a.profissional_id = %s"
                params.append(profissional_id)

            if data_inicio:
                query += " AND a.data_hora >= %s"
                params.append(data_inicio)

            if data_fim:
                query += " AND a.data_hora <= %s"
                params.append(data_fim)

            if telefone:
                query += " AND a.paciente_telefone = %s"
                params.append(telefone)

            query += " ORDER BY a.data_hora"

            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def _criar_agendamento_sync(profissional_id, paciente_nome, data_hora, telefone=None, nascimento=None, observacoes=None, conversation_id=None):
    """Cria agendamento (sincrono)"""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Verifica conflito
            cur.execute("""
                SELECT id, paciente_nome, data_hora
                FROM agendamentos
                WHERE profissional_id = %s
                AND status != 'cancelado'
                AND data_hora >= %s AND data_hora < %s
            """, (profissional_id, data_hora, data_hora + timedelta(minutes=30)))

            conflito = cur.fetchone()
            if conflito:
                return {"error": f"Horario ja ocupado por {conflito['paciente_nome']}"}

            # Cria o agendamento
            cur.execute("""
                INSERT INTO agendamentos
                (profissional_id, paciente_nome, paciente_telefone, paciente_nascimento,
                 data_hora, observacoes, conversation_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (profissional_id, paciente_nome, telefone, nascimento, data_hora, observacoes, conversation_id))

            result = cur.fetchone()
            agendamento_id = result["id"]
            conn.commit()

            # Atualiza o pipeline automaticamente para "agendado"
            if telefone:
                _atualizar_pipeline_sync(
                    telefone=telefone,
                    etapa="agendado",
                    nome_paciente=paciente_nome,
                    agendamento_id=agendamento_id
                )

            return {"id": agendamento_id}
    finally:
        conn.close()


def _buscar_agendamento_sync(agendamento_id):
    """Busca um agendamento por ID"""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT a.*, p.nome as profissional_nome, p.especialidade
                FROM agendamentos a
                JOIN profissionais p ON a.profissional_id = p.id
                WHERE a.id = %s
            """, (agendamento_id,))
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        conn.close()


def _atualizar_agendamento_sync(agendamento_id, data_hora=None, status=None, confirmado=None):
    """Atualiza agendamento (sincrono)"""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            updates = []
            params = []

            if data_hora:
                updates.append("data_hora = %s")
                params.append(data_hora)

            if status:
                updates.append("status = %s")
                params.append(status)

            if confirmado is not None:
                updates.append("confirmado = %s")
                params.append(confirmado)

            if not updates:
                return False

            updates.append("updated_at = NOW()")
            params.append(agendamento_id)

            cur.execute(f"""
                UPDATE agendamentos
                SET {', '.join(updates)}
                WHERE id = %s
            """, params)
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def _cancelar_agendamento_sync(agendamento_id, motivo=None):
    """Cancela agendamento (sincrono) e atualiza pipeline"""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Busca dados do agendamento antes de cancelar
            cur.execute("""
                SELECT paciente_telefone, paciente_nome
                FROM agendamentos
                WHERE id = %s
            """, (agendamento_id,))
            ag_data = cur.fetchone()

            # Atualiza o agendamento
            obs_cancelamento = f"Cancelado pelo paciente" if not motivo else f"Cancelado: {motivo}"
            cur.execute("""
                UPDATE agendamentos
                SET status = 'cancelado',
                    updated_at = NOW(),
                    observacoes = COALESCE(observacoes || ' | ', '') || %s
                WHERE id = %s
            """, (obs_cancelamento, agendamento_id))

            rows_affected = cur.rowcount

            # Se cancelou e tem telefone, atualiza o pipeline
            if rows_affected > 0 and ag_data and ag_data.get("paciente_telefone"):
                cur.execute("""
                    UPDATE pipeline_conversas
                    SET etapa = 'cancelado',
                        agendamento_id = NULL,
                        ultima_atualizacao = NOW()
                    WHERE telefone = %s
                """, (ag_data["paciente_telefone"],))

            conn.commit()
            return rows_affected > 0
    finally:
        conn.close()


def _confirmar_agendamento_sync(agendamento_id):
    """Confirma agendamento (sincrono)"""
    conn = _get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE agendamentos
                SET confirmado = true, status = 'confirmado', updated_at = NOW()
                WHERE id = %s
            """, (agendamento_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        conn.close()


def _atualizar_pipeline_sync(telefone, etapa=None, nome_paciente=None, agendamento_id=None):
    """Atualiza o pipeline de atendimento (sincrono)"""
    conn = _get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Verifica se ja existe
            cur.execute("""
                SELECT id FROM pipeline_conversas WHERE telefone = %s
            """, (telefone,))
            existing = cur.fetchone()

            if existing:
                # Atualiza
                updates = ["ultima_atualizacao = NOW()"]
                params = []

                if etapa:
                    updates.append("etapa = %s")
                    params.append(etapa)
                if nome_paciente:
                    updates.append("nome_paciente = %s")
                    params.append(nome_paciente)
                if agendamento_id is not None:
                    updates.append("agendamento_id = %s")
                    params.append(agendamento_id)

                params.append(telefone)
                cur.execute(f"""
                    UPDATE pipeline_conversas
                    SET {', '.join(updates)}
                    WHERE telefone = %s
                """, params)
            else:
                # Cria novo
                cur.execute("""
                    INSERT INTO pipeline_conversas
                    (telefone, etapa, nome_paciente, agendamento_id)
                    VALUES (%s, %s, %s, %s)
                """, (telefone, etapa or "novo_contato", nome_paciente, agendamento_id))

            conn.commit()
    finally:
        conn.close()


def _buscar_horarios_disponiveis_sync(profissional_id, data_obj):
    """Busca horarios disponiveis (sincrono)"""
    # Gera todos os slots do dia (8h as 18h, de 30 em 30 min)
    slots = []
    hora_atual = datetime.combine(data_obj, datetime.min.time().replace(hour=8))
    hora_fim = datetime.combine(data_obj, datetime.min.time().replace(hour=18))

    while hora_atual < hora_fim:
        slots.append(hora_atual)
        hora_atual += timedelta(minutes=30)

    # Busca agendamentos do dia
    inicio = datetime.combine(data_obj, datetime.min.time())
    fim = datetime.combine(data_obj, datetime.max.time())

    agendamentos = _buscar_agendamentos_sync(
        profissional_id=profissional_id,
        data_inicio=inicio,
        data_fim=fim
    )

    # Remove slots ocupados
    ocupados = set()
    for ag in agendamentos:
        ag_hora = ag["data_hora"]
        if isinstance(ag_hora, str):
            ag_hora = datetime.fromisoformat(ag_hora)
        # Remove timezone para comparacao
        if ag_hora.tzinfo:
            ag_hora = ag_hora.replace(tzinfo=None)
        ocupados.add(ag_hora.strftime("%H:%M"))

    disponiveis = [s.strftime("%H:%M") for s in slots if s.strftime("%H:%M") not in ocupados]

    # Se for hoje, remove horarios passados
    if data_obj == date.today():
        agora = datetime.now().strftime("%H:%M")
        disponiveis = [h for h in disponiveis if h > agora]

    return disponiveis


# ==================== FERRAMENTAS DO AGENTE ====================

@tool
def criar_agendamento(
    profissional_nome: Annotated[str, "Nome do profissional (ex: Dr. Joao Silva)"],
    paciente_nome: Annotated[str, "Nome completo do paciente"],
    data: Annotated[str, "Data do agendamento no formato YYYY-MM-DD"],
    horario: Annotated[str, "Horario no formato HH:MM (ex: 14:30)"],
    telefone: Annotated[str, "Telefone do paciente com DDD"],
    nascimento: Annotated[Optional[str], "Data de nascimento do paciente (YYYY-MM-DD)"] = None,
    observacoes: Annotated[Optional[str], "Observacoes adicionais"] = None,
    conversation_id: Annotated[Optional[str], "ID da conversa no Chatwoot"] = None
) -> str:
    """
    Cria um novo agendamento/consulta.
    Use para agendar novas consultas.
    Sempre inclua: nome do paciente, telefone e data de nascimento.
    """
    try:
        # Busca o profissional pelo nome
        profissionais = _listar_profissionais_sync()
        prof = None
        nome_lower = profissional_nome.lower()

        for p in profissionais:
            if nome_lower in p["nome"].lower():
                prof = p
                break

        if not prof:
            nomes = ', '.join([p['nome'] for p in profissionais]) if profissionais else "Nenhum cadastrado"
            return f"Profissional '{profissional_nome}' nao encontrado. Profissionais disponiveis: {nomes}"

        # Monta a data/hora SEM timezone (naive) para salvar o horário exato
        # O PostgreSQL vai tratar como horário local
        try:
            data_hora = datetime.strptime(f"{data} {horario}", "%Y-%m-%d %H:%M")
        except ValueError:
            return f"Formato de data/hora invalido. Use YYYY-MM-DD para data e HH:MM para horario."

        # Verifica se e data futura (compara com horário local)
        if data_hora < datetime.now():
            return "Erro: Nao e possivel agendar em datas/horarios passados."

        # Converte nascimento
        nasc = None
        if nascimento:
            try:
                nasc = date.fromisoformat(nascimento)
            except ValueError:
                pass  # Ignora se formato invalido

        # Cria o agendamento
        result = _criar_agendamento_sync(
            profissional_id=prof["id"],
            paciente_nome=paciente_nome,
            data_hora=data_hora,
            telefone=telefone,
            nascimento=nasc,
            observacoes=observacoes,
            conversation_id=conversation_id
        )

        if "error" in result:
            return f"Erro ao agendar: {result['error']}"

        return f"Agendamento criado com sucesso! ID: {result['id']}. Consulta marcada para {data_hora.strftime('%d/%m/%Y as %H:%M')} com {prof['nome']}."

    except Exception as e:
        return f"Erro ao criar agendamento: {str(e)}"


@tool
def buscar_horarios_disponiveis(
    profissional_nome: Annotated[str, "Nome do profissional"],
    data: Annotated[str, "Data para buscar horarios (YYYY-MM-DD)"]
) -> str:
    """
    Busca horarios disponiveis para agendamento em uma data especifica.
    Use para verificar disponibilidade antes de agendar.
    """
    try:
        # Busca o profissional
        profissionais = _listar_profissionais_sync()
        prof = None
        nome_lower = profissional_nome.lower()

        for p in profissionais:
            if nome_lower in p["nome"].lower():
                prof = p
                break

        if not prof:
            return f"Profissional '{profissional_nome}' nao encontrado."

        # Busca horarios
        try:
            data_obj = date.fromisoformat(data)
        except ValueError:
            return "Formato de data invalido. Use YYYY-MM-DD."

        horarios = _buscar_horarios_disponiveis_sync(
            profissional_id=prof["id"],
            data_obj=data_obj
        )

        if not horarios:
            return f"Nao ha horarios disponiveis para {data_obj.strftime('%d/%m/%Y')} com {prof['nome']}."

        # Formata a resposta
        data_formatada = data_obj.strftime("%d/%m/%Y")
        return f"Horarios disponiveis para {data_formatada} com {prof['nome']}:\n" + \
               "\n".join([f"- {h}" for h in horarios])

    except Exception as e:
        return f"Erro ao buscar horarios: {str(e)}"


@tool
def buscar_agendamento_paciente(
    telefone: Annotated[str, "Telefone do paciente para buscar agendamentos"]
) -> str:
    """
    Busca agendamentos futuros de um paciente pelo telefone.
    Use para verificar consultas ja marcadas.
    """
    try:
        agendamentos = _buscar_agendamentos_sync(
            telefone=telefone,
            data_inicio=datetime.now()
        )

        if not agendamentos:
            return "Nenhum agendamento futuro encontrado para este telefone."

        result = "Agendamentos encontrados:\n\n"
        for ag in agendamentos:
            data_hora = ag["data_hora"]
            if isinstance(data_hora, str):
                data_hora = datetime.fromisoformat(data_hora)

            status = "CONFIRMADO" if ag.get("confirmado") else ag.get("status", "agendado")
            result += f"- ID: {ag['id']}\n"
            result += f"  Paciente: {ag['paciente_nome']}\n"
            result += f"  Data: {data_hora.strftime('%d/%m/%Y as %H:%M')}\n"
            result += f"  Profissional: {ag.get('profissional_nome', 'N/A')}\n"
            result += f"  Status: {status}\n\n"

        return result

    except Exception as e:
        return f"Erro ao buscar agendamentos: {str(e)}"


@tool
def listar_agendamentos_dia(
    data: Annotated[str, "Data para listar agendamentos (YYYY-MM-DD)"],
    profissional_nome: Annotated[Optional[str], "Nome do profissional (opcional)"] = None
) -> str:
    """
    Lista todos os agendamentos de um dia especifico.
    Use para ver a agenda do dia.
    """
    try:
        # Busca o profissional se especificado
        prof_id = None
        if profissional_nome:
            profissionais = _listar_profissionais_sync()
            for p in profissionais:
                if profissional_nome.lower() in p["nome"].lower():
                    prof_id = p["id"]
                    break

        # Monta periodo do dia
        try:
            data_obj = date.fromisoformat(data)
        except ValueError:
            return "Formato de data invalido. Use YYYY-MM-DD."

        inicio = datetime.combine(data_obj, datetime.min.time())
        fim = datetime.combine(data_obj, datetime.max.time())

        agendamentos = _buscar_agendamentos_sync(
            profissional_id=prof_id,
            data_inicio=inicio,
            data_fim=fim
        )

        if not agendamentos:
            return f"Nenhum agendamento para {data_obj.strftime('%d/%m/%Y')}. Todos os horarios estao disponiveis."

        result = f"Agendamentos para {data_obj.strftime('%d/%m/%Y')}:\n\n"
        for ag in sorted(agendamentos, key=lambda x: x["data_hora"]):
            data_hora = ag["data_hora"]
            if isinstance(data_hora, str):
                data_hora = datetime.fromisoformat(data_hora)

            status = "CONFIRMADO" if ag.get("confirmado") else ag.get("status", "agendado")
            result += f"- {data_hora.strftime('%H:%M')} - {ag['paciente_nome']}"
            result += f" ({ag.get('profissional_nome', 'N/A')})"
            result += f" [{status}]\n"
            result += f"  ID: {ag['id']}\n\n"

        return result

    except Exception as e:
        return f"Erro ao listar agendamentos: {str(e)}"


@tool
def remarcar_agendamento(
    agendamento_id: Annotated[int, "ID do agendamento a remarcar"],
    nova_data: Annotated[str, "Nova data (YYYY-MM-DD)"],
    novo_horario: Annotated[str, "Novo horario (HH:MM)"]
) -> str:
    """
    Remarca um agendamento para nova data/horario.
    Use quando o paciente precisar remarcar a consulta.
    """
    try:
        # Busca o agendamento atual
        ag = _buscar_agendamento_sync(agendamento_id)
        if not ag:
            return f"Agendamento ID {agendamento_id} nao encontrado."

        # Monta nova data/hora SEM timezone (naive)
        try:
            nova_data_hora = datetime.strptime(f"{nova_data} {novo_horario}", "%Y-%m-%d %H:%M")
        except ValueError:
            return "Formato de data/hora invalido."

        if nova_data_hora < datetime.now():
            return "Erro: Nao e possivel remarcar para datas/horarios passados."

        # Atualiza
        success = _atualizar_agendamento_sync(
            agendamento_id=agendamento_id,
            data_hora=nova_data_hora
        )

        if not success:
            return "Erro ao remarcar agendamento."

        return f"Agendamento remarcado com sucesso! Nova data: {nova_data_hora.strftime('%d/%m/%Y as %H:%M')}."

    except Exception as e:
        return f"Erro ao remarcar: {str(e)}"


@tool
def cancelar_agendamento(
    agendamento_id: Annotated[int, "ID do agendamento a cancelar"],
    motivo: Annotated[Optional[str], "Motivo do cancelamento"] = None
) -> str:
    """
    Cancela um agendamento pelo ID.
    Use quando souber o ID do agendamento.
    """
    try:
        # Busca o agendamento
        ag = _buscar_agendamento_sync(agendamento_id)
        if not ag:
            return f"Agendamento ID {agendamento_id} nao encontrado."

        if ag.get("status") == "cancelado":
            return "Este agendamento ja esta cancelado."

        # Cancela
        success = _cancelar_agendamento_sync(agendamento_id, motivo)

        if not success:
            return "Erro ao cancelar agendamento."

        data_hora = ag["data_hora"]
        if isinstance(data_hora, str):
            data_hora = datetime.fromisoformat(data_hora)

        return f"Agendamento cancelado com sucesso! Consulta de {ag['paciente_nome']} em {data_hora.strftime('%d/%m/%Y as %H:%M')} foi cancelada."

    except Exception as e:
        return f"Erro ao cancelar: {str(e)}"


@tool
def cancelar_agendamento_paciente(
    telefone: Annotated[str, "Telefone do paciente com DDD"],
    confirmar: Annotated[bool, "True para confirmar o cancelamento"] = False,
    motivo: Annotated[Optional[str], "Motivo do cancelamento"] = None
) -> str:
    """
    Cancela o proximo agendamento de um paciente pelo telefone.
    Use quando o paciente pedir para cancelar sua consulta.
    IMPORTANTE: Primeiro chame com confirmar=False para mostrar os dados ao paciente.
    Depois chame novamente com confirmar=True apos o paciente confirmar.
    """
    try:
        # Busca agendamentos futuros do paciente
        agendamentos = _buscar_agendamentos_sync(
            telefone=telefone,
            data_inicio=datetime.now()
        )

        if not agendamentos:
            return "Nenhum agendamento futuro encontrado para este telefone. Nao ha nada para cancelar."

        # Se tem mais de um agendamento, lista todos
        if len(agendamentos) > 1 and not confirmar:
            result = f"Encontrei {len(agendamentos)} agendamentos futuros:\n\n"
            for ag in agendamentos:
                data_hora = ag["data_hora"]
                if isinstance(data_hora, str):
                    data_hora = datetime.fromisoformat(data_hora)
                result += f"- ID {ag['id']}: {data_hora.strftime('%d/%m/%Y as %H:%M')} com {ag.get('profissional_nome', 'N/A')}\n"
            result += "\nPergunta ao paciente qual agendamento deseja cancelar e use a ferramenta cancelar_agendamento com o ID especifico."
            return result

        # Pega o proximo agendamento
        ag = agendamentos[0]
        data_hora = ag["data_hora"]
        if isinstance(data_hora, str):
            data_hora = datetime.fromisoformat(data_hora)

        if ag.get("status") == "cancelado":
            return "O agendamento ja esta cancelado."

        # Se nao confirmou ainda, mostra os dados e pede confirmacao
        if not confirmar:
            return (f"Encontrei o seguinte agendamento:\n"
                    f"- Paciente: {ag['paciente_nome']}\n"
                    f"- Data: {data_hora.strftime('%d/%m/%Y as %H:%M')}\n"
                    f"- Profissional: {ag.get('profissional_nome', 'N/A')}\n"
                    f"- ID: {ag['id']}\n\n"
                    f"Pergunte ao paciente se deseja confirmar o cancelamento. "
                    f"Se sim, chame novamente esta ferramenta com confirmar=True.")

        # Confirma o cancelamento
        success = _cancelar_agendamento_sync(ag["id"], motivo)

        if not success:
            return "Erro ao cancelar agendamento."

        return (f"Agendamento cancelado com sucesso!\n"
                f"Consulta de {ag['paciente_nome']} em {data_hora.strftime('%d/%m/%Y as %H:%M')} "
                f"com {ag.get('profissional_nome', 'N/A')} foi cancelada.\n"
                f"O paciente pode agendar uma nova consulta quando desejar.")

    except Exception as e:
        return f"Erro ao cancelar: {str(e)}"


@tool
def confirmar_agendamento(
    agendamento_id: Annotated[int, "ID do agendamento a confirmar"]
) -> str:
    """
    Confirma um agendamento.
    Use quando o paciente confirmar a presenca na consulta.
    """
    try:
        # Busca o agendamento
        ag = _buscar_agendamento_sync(agendamento_id)
        if not ag:
            return f"Agendamento ID {agendamento_id} nao encontrado."

        if ag.get("confirmado"):
            return "Este agendamento ja esta confirmado."

        # Confirma
        success = _confirmar_agendamento_sync(agendamento_id)

        if not success:
            return "Erro ao confirmar agendamento."

        data_hora = ag["data_hora"]
        if isinstance(data_hora, str):
            data_hora = datetime.fromisoformat(data_hora)

        return f"Agendamento confirmado com sucesso! Consulta de {ag['paciente_nome']} em {data_hora.strftime('%d/%m/%Y as %H:%M')} esta confirmada."

    except Exception as e:
        return f"Erro ao confirmar: {str(e)}"


@tool
def listar_profissionais_disponiveis() -> str:
    """
    Lista todos os profissionais disponiveis para agendamento.
    Use para informar ao paciente quais profissionais atendem na empresa.
    """
    try:
        profissionais = _listar_profissionais_sync()

        if not profissionais:
            return "Nenhum profissional cadastrado no momento."

        result = "Profissionais disponiveis:\n\n"
        for p in profissionais:
            result += f"- {p['nome']}"
            if p.get("cargo"):
                result += f" ({p['cargo']})"
            if p.get("especialidade"):
                result += f" - {p['especialidade']}"
            result += "\n"

        return result

    except Exception as e:
        return f"Erro ao listar profissionais: {str(e)}"


@tool
def registrar_nome_paciente(
    nome: Annotated[str, "Nome completo do paciente"],
    telefone: Annotated[str, "Telefone do paciente com DDD"]
) -> str:
    """
    Registra o nome do paciente no sistema.
    Use quando o paciente informar seu nome durante a conversa.
    Isso atualiza o cadastro do paciente no pipeline de atendimento.
    """
    try:
        _atualizar_pipeline_sync(
            telefone=telefone,
            nome_paciente=nome
        )
        return f"Nome '{nome}' registrado com sucesso para o telefone {telefone}."
    except Exception as e:
        return f"Erro ao registrar nome: {str(e)}"


# Lista de ferramentas de agenda
AGENDA_TOOLS = [
    criar_agendamento,
    buscar_horarios_disponiveis,
    buscar_agendamento_paciente,
    listar_agendamentos_dia,
    remarcar_agendamento,
    cancelar_agendamento,
    cancelar_agendamento_paciente,
    confirmar_agendamento,
    listar_profissionais_disponiveis,
    registrar_nome_paciente
]
