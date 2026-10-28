"""C4 test model advice_strip.cae: aluminium strip 200 x 20 (x 0..200, y 0..20), thickness 2 along z.
Units mm, tonne, s. Aluminium elastic only, no steps/BCs/loads/mesh."""
from abaqus import *
from abaqusConstants import *
from caeModules import *

m = mdb.models["Model-1"]
mat = m.Material(name="Aluminium")
mat.Elastic(table=((70000.0, 0.33),))
mat.Density(table=((2.7e-9,),))
m.HomogeneousSolidSection(name="Sec", material="Aluminium", thickness=None)

s = m.ConstrainedSketch(name="sc", sheetSize=400.0)
s.rectangle(point1=(0.0, 0.0), point2=(200.0, 20.0))
strip = m.Part(name="Strip", dimensionality=THREE_D, type=DEFORMABLE_BODY)
strip.BaseSolidExtrude(sketch=s, depth=2.0)
strip.Set(cells=strip.cells, name="ALL")
strip.SectionAssignment(region=strip.sets["ALL"], sectionName="Sec")

m.rootAssembly.Instance(name="Strip-1", part=strip, dependent=ON)
mdb.saveAs(pathName="advice_strip.cae")
