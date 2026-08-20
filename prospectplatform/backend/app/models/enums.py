import enum


class CompanySource(str, enum.Enum):
    GOOGLE_MAPS = "google_maps"
    CSV_IMPORT = "csv_import"


class AuditPriority(str, enum.Enum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class OpportunityStatus(str, enum.Enum):
    PENDENTE = "pendente"
    APROVADA = "aprovada"
    REJEITADA = "rejeitada"


class MessageStatus(str, enum.Enum):
    RASCUNHO = "rascunho"
    APROVADA = "aprovada"
    ENVIADA = "enviada"


class ProspectingStatus(str, enum.Enum):
    NOVO = "NOVO"
    QUALIFICADO = "QUALIFICADO"
    AUDITADO = "AUDITADO"
    ABORDAGEM_PENDENTE = "ABORDAGEM_PENDENTE"
    CONTATADO = "CONTATADO"
    RESPONDEU = "RESPONDEU"
    INTERESSADO = "INTERESSADO"
    PROPOSTA = "PROPOSTA"
    GANHO = "GANHO"
    PERDIDO = "PERDIDO"


PROSPECTING_TRANSITIONS: dict[str, list[str]] = {
    ProspectingStatus.NOVO.value: [ProspectingStatus.QUALIFICADO.value],
    ProspectingStatus.QUALIFICADO.value: [ProspectingStatus.AUDITADO.value],
    ProspectingStatus.AUDITADO.value: [ProspectingStatus.ABORDAGEM_PENDENTE.value],
    ProspectingStatus.ABORDAGEM_PENDENTE.value: [ProspectingStatus.CONTATADO.value],
    ProspectingStatus.CONTATADO.value: [ProspectingStatus.RESPONDEU.value, ProspectingStatus.PERDIDO.value],
    ProspectingStatus.RESPONDEU.value: [ProspectingStatus.INTERESSADO.value, ProspectingStatus.PERDIDO.value],
    ProspectingStatus.INTERESSADO.value: [ProspectingStatus.PROPOSTA.value, ProspectingStatus.PERDIDO.value],
    ProspectingStatus.PROPOSTA.value: [ProspectingStatus.GANHO.value, ProspectingStatus.PERDIDO.value],
    ProspectingStatus.GANHO.value: [],
    ProspectingStatus.PERDIDO.value: [],
}
