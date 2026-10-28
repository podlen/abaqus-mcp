"""Kernel script that builds the C3 test model summary_test.cae (run by the E2E test through
run_script). Units mm, N, MPa. Known contents, by construction:
  Billet  3D deformable cylinder R10 x 20, not meshed, not instanced
  Axi     AXI deformable rectangle 10 x 10, CAX4R 4 x 4, instance Axi-1 (dependent)
  Plate   AXI analytic rigid line y = 10, x 0..12, reference point (0, 10), instance Plate-1
Model "Solid" (instances cannot mix 3D and axisymmetric in one model):
  Block   3D box 2 x 2 x 2, C3D8R 2 x 2 x 2, instance Block-1 translated by (5, 0, 3) (independent, meshed on the instance), material Steel
"""
from abaqus import *
from abaqusConstants import *
from caeModules import *
import mesh

m = mdb.models["Model-1"]
m2 = mdb.Model(name="Solid")

# Billet
s = m.ConstrainedSketch(name="sb", sheetSize=50.0)
s.CircleByCenterPerimeter(center=(0.0, 0.0), point1=(10.0, 0.0))
billet = m.Part(name="Billet", dimensionality=THREE_D, type=DEFORMABLE_BODY)
billet.BaseSolidExtrude(sketch=s, depth=20.0)
billet.Set(faces=billet.faces.findAt(((0.0, 0.0, 20.0),)), name="TOPFACE")

# Axi
s = m.ConstrainedSketch(name="sa", sheetSize=50.0)
s.assignCenterline(line=s.ConstructionLine(point1=(0.0, -50.0), point2=(0.0, 50.0)))
s.rectangle(point1=(0.0, 0.0), point2=(10.0, 10.0))
axi = m.Part(name="Axi", dimensionality=AXISYMMETRIC, type=DEFORMABLE_BODY)
axi.BaseShell(sketch=s)
axi.Set(faces=axi.faces, name="ALL")
axi.Surface(side1Edges=axi.edges.findAt(((5.0, 10.0, 0.0),)), name="TOPS")
axi.seedPart(size=2.5)
axi.setElementType(regions=(axi.faces,), elemTypes=(mesh.ElemType(elemCode=CAX4R, elemLibrary=STANDARD),))
axi.generateMesh()

# Plate
s = m.ConstrainedSketch(name="sp", sheetSize=50.0)
s.assignCenterline(line=s.ConstructionLine(point1=(0.0, -50.0), point2=(0.0, 50.0)))
s.Line(point1=(0.0, 10.0), point2=(12.0, 10.0))
plate = m.Part(name="Plate", dimensionality=AXISYMMETRIC, type=ANALYTIC_RIGID_SURFACE)
plate.AnalyticRigidSurf2DPlanar(sketch=s)
plate.ReferencePoint(point=(0.0, 10.0, 0.0))
plate.Surface(side1Edges=plate.edges, name="FACE")

# material, section, assignments
mat = m.Material(name="Steel")
mat.Elastic(table=((210000.0, 0.3),))
mat.Plastic(table=((250.0, 0.0), (300.0, 0.1)))
mat.Density(table=((7.85e-9,),))
m.HomogeneousSolidSection(name="Sec", material="Steel", thickness=None)
axi.SectionAssignment(region=axi.sets["ALL"], sectionName="Sec")

# assembly
a = m.rootAssembly
ia = a.Instance(name="Axi-1", part=axi, dependent=ON)
ip = a.Instance(name="Plate-1", part=plate, dependent=ON)
a.Set(edges=ia.edges.findAt(((5.0, 0.0, 0.0),)), name="SYM")
a.Set(referencePoints=(ip.referencePoints[ip.referencePoints.keys()[0]],), name="RP")
a.Surface(side1Edges=ia.edges.findAt(((5.0, 10.0, 0.0),)), name="TOP_AXI")
a.Surface(side1Edges=ip.edges, name="PLATE_S")

# step, BC, load, contact
m.StaticStep(name="Upset", previous="Initial", nlgeom=ON, timePeriod=1.0, initialInc=0.01,
             minInc=1e-6, maxInc=0.1, maxNumInc=500)
m.DisplacementBC(name="Symm", createStepName="Initial", region=a.sets["SYM"], u2=0.0)
m.ConcentratedForce(name="Push", createStepName="Upset", region=a.sets["RP"], cf2=-1000.0)
cp = m.ContactProperty("fric")
cp.TangentialBehavior(formulation=PENALTY, table=((0.1,),), fraction=0.005, elasticSlipStiffness=None)
cp.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON)
m.SurfaceToSurfaceContactStd(name="Cont", createStepName="Upset", main=a.surfaces["PLATE_S"],
                             secondary=a.surfaces["TOP_AXI"], sliding=FINITE, interactionProperty="fric")
# Block
s = m2.ConstrainedSketch(name="sk", sheetSize=50.0)
s.rectangle(point1=(0.0, 0.0), point2=(2.0, 2.0))
block = m2.Part(name="Block", dimensionality=THREE_D, type=DEFORMABLE_BODY)
block.BaseSolidExtrude(sketch=s, depth=2.0)
block.Set(cells=block.cells, name="ALL")

m2.Material(name="Steel").Elastic(table=((210000.0, 0.3),))
m2.HomogeneousSolidSection(name="Sec", material="Steel", thickness=None)
block.SectionAssignment(region=block.sets["ALL"], sectionName="Sec")
a2 = m2.rootAssembly
ib = a2.Instance(name="Block-1", part=block, dependent=OFF)
a2.translate(instanceList=("Block-1",), vector=(5.0, 0.0, 3.0))
a2.seedPartInstance(regions=(ib,), size=1.0)
a2.setElementType(regions=(ib.cells,), elemTypes=(mesh.ElemType(elemCode=C3D8R, elemLibrary=STANDARD),))
a2.generateMesh(regions=(ib,))
mdb.saveAs(pathName="summary_test.cae")
