"""File layout under DATA_DIR: <cliente>/<fechamento>/{entrada,saida,saida-rev-N}. Nothing resolves outside DATA_DIR."""
from pathlib import Path


def _safe(settings, *parts):
    root = Path(settings.data_dir).resolve()
    for part in parts:
        text = str(part)
        if not text or text in ('.','..') or '/' in text or '\\' in text or '\x00' in text:
            raise ValueError(f'Caminho inválido: {text!r}')
    path = root.joinpath(*(str(part) for part in parts)).resolve()
    if path != root and not path.is_relative_to(root):
        raise ValueError('Caminho fora de DATA_DIR')
    return path


def closing_dir(settings, cliente_id, fechamento_id):
    return _safe(settings,cliente_id,fechamento_id)


def input_dir(settings, cliente_id, fechamento_id):
    return _safe(settings,cliente_id,fechamento_id,'entrada')


def output_dir(settings, cliente_id, fechamento_id):
    return _safe(settings,cliente_id,fechamento_id,'saida')


def revision_dir(settings, cliente_id, fechamento_id, numero):
    return _safe(settings,cliente_id,fechamento_id,f'saida-rev-{int(numero)}')
