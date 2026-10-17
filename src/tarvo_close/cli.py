import argparse
import json
from pathlib import Path
import sys

from .closing import close_month
from .readers import read_inputs
from .reporting import publish_result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Generate a traceable monthly closing from the source files, using the finance team rules.')
    parser.add_argument('--input',type=Path,default=Path('Tarvo_Data_Pack_set2026'))
    parser.add_argument('--policy',type=Path,default=Path('config/closing-policy.json'))
    parser.add_argument('--period',required=True)
    parser.add_argument('--output',type=Path,default=Path('saida'))
    args = parser.parse_args(argv)
    try:
        policy = json.loads(args.policy.read_text(encoding='utf-8'))
        bundle = read_inputs(args.input)
        result = close_month(bundle,policy,args.period)
        manifest = publish_result(bundle,result,policy,args.period,args.output)
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Closing failed: {error}',file=sys.stderr)
        return 1
    metrics = result.metrics
    print(f'Closing saved: {args.output.resolve()}')
    print(f'Run: {manifest["run_id"]}')
    print(f'Checkout commission: BRL {metrics["comissao_checkout"]}')
    print(f'Remittance participation: BRL {metrics["participacao_remessas"]}')
    print(f'Invoices to issue after review: {metrics["notas"]}; BRL {metrics["valor_notas"]}')
    print(f'Rate divergences: {metrics["divergencias"]}; Orbe BRL {metrics["diferenca_checkout_brl"]}; Ponte BRL {metrics["diferenca_remessa_brl"]}')
    print(f'Pending items: {metrics["pendencias"]}. Open {args.output / "index.html"} to review.')
    return 0
