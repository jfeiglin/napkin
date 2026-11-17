"""E1: the equality (KKT) solve toward `near`, at scale. Normal equations against the augmented system."""
import time, sys
import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import splu, spsolve
from net import network, incidence

def clock(label, fn, repeat=1):
    best = 1e9
    for _ in range(repeat):
        t = time.perf_counter(); out = fn(); best = min(best, time.perf_counter() - t)
    print(f'{label:55s} {best*1000:9.1f} ms')
    return out

def problem(net, up=None, theta_range=20.0):
    """Unknowns x = (theta[P], p[S]) with served pinned at need. A x = need.
    Row i: sum_g p_g  - sum_l C[l,i] * b_l * (C theta)_l = need_i  ->  G p - (C^T B C) theta = need."""
    P, S = net['places'], net['sources']
    C = incidence(net)
    b = net['b'] if up is None else net['b'] * up
    L = (C.T @ sp.diags_array(b) @ C).tocsr()
    G = sp.coo_array((np.ones(S), (net['at'], np.arange(S))), shape=(P, S)).tocsr()
    A = sp.hstack([-L, G]).tocsr()
    w = np.r_[np.full(P, 1.0 / theta_range**2), 1.0 / net['pmax'] ** 2]
    near = np.r_[np.zeros(P), net['p0']]
    return A, w, near, net['need'].copy()

def normal(A, w, near, rhs, spec='MMD_AT_PLUS_A'):
    M = (A @ sp.diags_array(1.0 / w) @ A.T).tocsc()
    lu = splu(M, permc_spec=spec, diag_pivot_thresh=0.0, options=dict(SymmetricMode=True))
    lam = lu.solve(A @ near - rhs)
    return near - (A.T @ lam) / w, lu, M

def augmented(A, w, near, rhs, delta=0.0, spec='MMD_AT_PLUS_A'):
    n, m = len(w), A.shape[0]
    K = sp.block_array([[sp.diags_array(w), A.T], [A, -delta * sp.eye_array(m) if delta else None]]).tocsc()
    lu = splu(K, permc_spec=spec)
    sol = lu.solve(np.r_[w * near, rhs])
    return sol[:n], lu, K

if __name__ == '__main__':
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    net = network(int(30000 * scale), int(35000 * scale), int(15000 * scale))
    A, w, near, rhs = clock('assemble', lambda: problem(net))
    print('A', A.shape, A.nnz)
    for spec in ('MMD_AT_PLUS_A', 'COLAMD', 'MMD_ATA'):
        try:
            x, lu, M = clock(f'normal equations: factor+solve [{spec}]', lambda: normal(A, w, near, rhs, spec))
            print('   nnz(M)', M.nnz, 'nnz(L+U)', lu.L.nnz + lu.U.nnz, 'residual', np.abs(A @ x - rhs).max())
        except Exception as e:
            print(spec, 'failed', e)
    x, lu, M = normal(A, w, near, rhs)
    r = A @ near - rhs
    clock('normal equations: back-substitution only', lambda: lu.solve(r), 5)
    xa, lua, K = clock('augmented system: factor+solve [MMD_AT_PLUS_A]', lambda: augmented(A, w, near, rhs))
    print('   nnz(K)', K.nnz, 'nnz(L+U)', lua.L.nnz + lua.U.nnz, 'residual', np.abs(A @ xa - rhs).max(), 'diff', np.abs(x - xa).max())
    clock('augmented: back-substitution only', lambda: lua.solve(np.r_[w * near, rhs]), 5)
    P = net['places']
    p = x[P:]
    print('sources outside range:', int((p < 0).sum()), int((p > net['pmax']).sum()), 'of', len(p))
    flow = net['b'] * (incidence(net) @ x[:P])
    print('angle range', x[:P].min(), x[:P].max(), 'max |flow|', np.abs(flow).max())
