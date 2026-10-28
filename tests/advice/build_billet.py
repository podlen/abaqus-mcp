"""C4 test model advice_billet.cae: cylinder Billet D20 x H20 between two plates 40 x 40 x 5
(PlateBottom z -5..0, Billet z 0..20, PlateTop z 20..25). Units mm. Steel elastic only, no steps/BCs/loads/mesh."""
from abaqus import *
from abaqusConstants import *
from caeModules import *

m = mdb.models["Model-1"]
m.Material(name="Steel").Elastic(table=((210000.0, 0.3),))
m.HomogeneousSolidSection(name="Sec", material="Steel", thickness=None)

s = m.ConstrainedSketch(name="sb", sheetSize=50.0)
s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(10.0, 0.0))
billet = m.Part(name="Billet", dimensionality=THREE_D, type=DEFORMABLE_BODY)
billet.BaseSolidExtrude(sketch=s, depth=20.0)

parts = [billet]
for name in ("PlateTop", "PlateBottom"):
    s = m.ConstrainedSketch(name="s" + name, sheetSize=100.0)
    s.rectangle(point1=(-20.0, -20.0), point2=(20.0, 20.0))
    p = m.Part(name=name, dimensionality=THREE_D, type=DEFORMABLE_BODY)
    p.BaseSolidExtrude(sketch=s, depth=5.0)
    parts.append(p)

for p in parts:
    p.Set(cells=p.cells, name="ALL")
    p.SectionAssignment(region=p.sets["ALL"], sectionName="Sec")

a = m.rootAssembly
a.Instance(name="Billet-1", part=billet, dependent=ON)
ib = a.Instance(name="PlateBottom-1", part=m.parts["PlateBottom"], dependent=ON)
it = a.Instance(name="PlateTop-1", part=m.parts["PlateTop"], dependent=ON)
a.translate(instanceList=("PlateBottom-1",), vector=(0.0, 0.0, -5.0))
a.translate(instanceList=("PlateTop-1",), vector=(0.0, 0.0, 20.0))
mdb.saveAs(pathName="advice_billet.cae")
