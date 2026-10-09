"""Decisão pura: caixas detectadas entram, comando de movimento sai."""


def decidir_acao(objects, largura_frame=320):
    if not objects:
        return "s"
    if largura_frame <= 0:
        raise ValueError("Largura do frame deve ser positiva")
    box, _ = max(objects, key=lambda item: item[0][2] * item[0][3])
    center = box[0] + box[2] // 2
    zone = largura_frame // 3
    if center < zone:
        return "a"
    if center > 2 * zone:
        return "d"
    return "w"
