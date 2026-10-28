"""C4 test model advice_plate.cae: plate 200 x 100 x 2 (x -100..100, y -50..50, z 0..2) with a
central through-hole D20. Units mm. Steel elastic only, no steps/BCs/loads/mesh."""
from abaqus import *
from abaqusConstants import *
from caeModules import *

m = mdb.models["Model-1"]
m.Material(name="Steel").Elastic(table=((210000.0, 0.3),))
m.HomogeneousSolidSection(name="Sec", material="Steel", thickness=None)

s = m.ConstrainedSketch(name="sp", sheetSize=300.0)
s.rectangle(point1=(-100.0, -50.0), point2=(100.0, 50.0))
s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(10.0, 0.0))
plate = m.Part(name="Plate", dimensionality=THREE_D, type=DEFORMABLE_BODY)
plate.BaseSolidExtrude(sketch=s, depth=2.0)
plate.Set(cells=plate.cells, name="ALL")
plate.SectionAssignment(region=plate.sets["ALL"], sectionName="Sec")

m.rootAssembly.Instance(name="Plate-1", part=plate, dependent=ON)
mdb.saveAs(pathName="advice_plate.cae")
