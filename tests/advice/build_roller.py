"""Test model advice_roller.cae: steel roller (radius 10, axis along z) resting on a block 40 x 20 (x -20..20, y 0..20).
Both depth 20 along z. Roller-1 translated (0, 30, 0): axis through (x, y) = (0, 30), tangent to block top y = 20 along x = 0.
Units mm, N, MPa. Steel elastic only, no steps/BCs/loads/interactions/mesh."""
from abaqus import *
from abaqusConstants import *
from caeModules import *

m = mdb.models["Model-1"]
mat = m.Material(name="Steel")
mat.Elastic(table=((210000.0, 0.3),))
m.HomogeneousSolidSection(name="RollerSection", material="Steel", thickness=None)
m.HomogeneousSolidSection(name="BlockSection", material="Steel", thickness=None)

s = m.ConstrainedSketch(name="sr", sheetSize=100.0)
s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(10.0, 0.0))
roller = m.Part(name="Roller", dimensionality=THREE_D, type=DEFORMABLE_BODY)
roller.BaseSolidExtrude(sketch=s, depth=20.0)
roller.Set(cells=roller.cells, name="ALL")
roller.SectionAssignment(region=roller.sets["ALL"], sectionName="RollerSection")

s = m.ConstrainedSketch(name="sb", sheetSize=100.0)
s.rectangle(point1=(-20.0, 0.0), point2=(20.0, 20.0))
block = m.Part(name="Block", dimensionality=THREE_D, type=DEFORMABLE_BODY)
block.BaseSolidExtrude(sketch=s, depth=20.0)
block.Set(cells=block.cells, name="ALL")
block.SectionAssignment(region=block.sets["ALL"], sectionName="BlockSection")

a = m.rootAssembly
a.Instance(name="Block-1", part=block, dependent=ON)
a.Instance(name="Roller-1", part=roller, dependent=ON)
a.translate(instanceList=("Roller-1",), vector=(0.0, 30.0, 0.0))
mdb.saveAs(pathName="advice_roller.cae")
