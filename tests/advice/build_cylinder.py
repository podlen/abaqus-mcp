"""C4 test model advice_cylinder.cae: thick-walled hollow cylinder, inner radius 20, outer radius 40,
length 100 along z. Units mm. Steel elastic only, no steps/BCs/loads/mesh."""
from abaqus import *
from abaqusConstants import *
from caeModules import *

m = mdb.models["Model-1"]
m.Material(name="Steel").Elastic(table=((210000.0, 0.3),))
m.HomogeneousSolidSection(name="Sec", material="Steel", thickness=None)

s = m.ConstrainedSketch(name="sc", sheetSize=200.0)
s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(40.0, 0.0))
s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(20.0, 0.0))
cyl = m.Part(name="Cylinder", dimensionality=THREE_D, type=DEFORMABLE_BODY)
cyl.BaseSolidExtrude(sketch=s, depth=100.0)
cyl.Set(cells=cyl.cells, name="ALL")
cyl.SectionAssignment(region=cyl.sets["ALL"], sectionName="Sec")

m.rootAssembly.Instance(name="Cylinder-1", part=cyl, dependent=ON)
mdb.saveAs(pathName="advice_cylinder.cae")
