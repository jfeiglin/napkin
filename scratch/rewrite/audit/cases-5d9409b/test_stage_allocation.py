"""A stage changes an existing endpoint policy at re-share, including restoring proportional service."""
import pytest
from napkin.engine import read, run
from napkin.model.compile import compile_text

BASE = '''scenario "Switch service"
    horizon 2 h
w:
{body}
w.pump.start()
'''

@pytest.mark.parametrize('local', [False, True], ids=['member-store','occurrence-store'])
@pytest.mark.parametrize(('policy','expected'), [('priority', (2,1)), ('proportional',(1,2))])
def test_switch_endpoint_policy_in_a_stage(local, policy, expected):
    start = '' if local else 'this.'
    target = start + 'stock.outflow.allocation'
    after = f'priority({start}first)' if policy == 'priority' else 'proportional()'
    declarations = f"""stock: L = 20 L in [0 L,]
    outflow.capacity = 3 L/h
    outflow.allocation = priority({start}second)
flow first: {start}stock -> SINK
    request = 2 L/h
flow second: {start}stock -> SINK
    request = 4 L/h"""
    member = [] if local else ['    ' + line for line in declarations.splitlines()]
    event = ['    pump = event():']
    if local:
        event += ['        ' + line for line in declarations.splitlines()]
    event += ['        after 1 h:', f'            {target} = {after}', '        after 3 h']
    program = compile_text(BASE.format(body='\n'.join(member+event)), {'h':{'time':1},'L':{'volume':1}})
    record = run(program.program,program.configuration)
    assert record.failure is None
    owner = 'w.pump#0' if local else 'w'
    first, second = read(record,program.program,[owner+'.first.actual_rate', owner+'.second.actual_rate'],[.5,1.5])
    assert (first.values,second.values) == ((0,expected[0]),(3,expected[1]))
