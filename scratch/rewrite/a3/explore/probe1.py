import numpy as np, scipy.sparse as sp, time
from scipy.optimize._highspy import _core as h
print(h.HIGHS_VERSION_MAJOR, h.HIGHS_VERSION_MINOR, h.HIGHS_VERSION_PATCH)
s = h._Highs()
o = h.HighsOptions(); o.output_flag = False; o.log_to_console = False; o.threads = 1
s.passOptions(o)
inf = h.kHighsInf
# min -x0 - x1 s.t. x0 + x1 <= 3, 0<=x<=2
lp = h.HighsLp()
A = sp.csc_array(np.array([[1.0, 1.0]]))
lp.num_col_, lp.num_row_ = 2, 1
lp.a_matrix_.num_col_, lp.a_matrix_.num_row_ = 2, 1
lp.a_matrix_.format_ = h.MatrixFormat.kColwise
lp.a_matrix_.start_ = A.indptr.astype(np.int32); lp.a_matrix_.index_ = A.indices.astype(np.int32); lp.a_matrix_.value_ = A.data
lp.col_cost_ = np.array([-1.0, -1.0]); lp.col_lower_ = np.zeros(2); lp.col_upper_ = np.array([2.0, 2.0])
lp.row_lower_ = np.array([-inf]); lp.row_upper_ = np.array([3.0])
print(s.passModel(lp))
print(s.run(), s.getModelStatus())
sol = s.getSolution(); print('x', list(sol.col_value), 'col_dual', list(sol.col_dual), 'row_value', list(sol.row_value), 'row_dual', list(sol.row_dual))
b = s.getBasis(); print('basis valid', b.valid, list(b.col_status), list(b.row_status))
info = s.getInfo(); print(info.objective_function_value, info.simplex_iteration_count, info.basis_validity)
# add a column
print('addCol', s.addCol(-1.0, 0.0, 2.0, 1, np.array([0], dtype=np.int32), np.array([1.0])))
b = s.getBasis(); print('basis valid after addCol', b.valid, list(b.col_status), list(b.row_status))
print(s.run(), s.getModelStatus()); sol = s.getSolution(); print('x', list(sol.col_value)); print('iters', s.getInfo().simplex_iteration_count)
# add a row
print('addRow', s.addRow(-inf, 1.0, 2, np.array([0, 2], dtype=np.int32), np.array([1.0, 1.0])))
b = s.getBasis(); print('basis valid after addRow', b.valid, list(b.col_status), list(b.row_status))
print(s.run(), s.getModelStatus()); sol = s.getSolution(); print('x', list(sol.col_value)); print('iters', s.getInfo().simplex_iteration_count)
# delete a column
try:
    print('deleteCols', s.deleteCols(1, np.array([0], dtype=np.int32)))
except Exception as e:
    print('deleteCols err', e)
b = s.getBasis(); print('basis valid after deleteCols', b.valid, list(b.col_status), list(b.row_status))
print(s.run(), s.getModelStatus()); sol = s.getSolution(); print('x', list(sol.col_value)); print('iters', s.getInfo().simplex_iteration_count)
try:
    print('deleteRows', s.deleteRows(1, np.array([1], dtype=np.int32)))
except Exception as e:
    print('deleteRows err', e)
b = s.getBasis(); print('basis valid after deleteRows', b.valid, list(b.col_status), list(b.row_status))
print(s.run(), s.getModelStatus()); sol = s.getSolution(); print('x', list(sol.col_value)); print('iters', s.getInfo().simplex_iteration_count)
print(s.getNumCol(), s.getNumRow())
import inspect
for name in ('addCols','addRows','deleteCols','deleteRows','changeColsBounds','changeRowBounds','changeCoeff','setBasis','addLinearObjective','getRanging','changeColsCost','setSolution','getCol','getRow','getCols','getRows'):
    print(name, getattr(h._Highs, name).__doc__)
