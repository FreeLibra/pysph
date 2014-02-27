""" 3D Dam Break Over a dry bed. The case is described as a SPHERIC
benchmark https://wiki.manchester.ac.uk/spheric/index.php/Test2)


Setup:
------



x                   x !
x                   x !
x                   x !
x                   x !
x  o   o   o        x !
x    o   o          x !3m
x  o   o   o        x !
x    o   o          x !
x  o   o   o        x !
x                   x !
xxxxxxxxxxxxxxxxxxxxx |        o -- Fluid Particles
                               x -- Solid Particles
     -dx-                      dx = dy
_________4m___________

Y
|
|
|
|
|
|      /Z
|     /
|    /
|   /
|  /
| /
|/_________________X

Fluid particles are placed on a staggered grid. The nodes of the grid
are located at R = l*dx i + m * dy j with a two point bias (0,0) and
(dx/2, dy/2) refered to the corner defined by R. l and m are integers
and i and j are the unit vectors alon `X` and `Y` respectively.

For the Monaghan Type Repulsive boundary condition, a single row of
boundary particles is used with a boundary spacing delp = dx = dy.

For the Dynamic Boundary Conditions, a staggered grid arrangement is
used for the boundary particles.

Numerical Parameters:
---------------------

dx = dy = 0.012m
h = 0.0156 => h/dx = 1.3

Height of Water column = 2m
Length of Water column = 1m

Number of particles = 27639 + 1669 = 29308


ro = 1000.0
co = 10*sqrt(2*9.81*2) ~ 65.0
gamma = 7.0

Artificial Viscosity:
alpha = 0.5

XSPH Correction:
eps = 0.5

 """
import numpy
from db_geometry import DamBreak3DGeometry

from pysph.base.kernels import CubicSpline, WendlandQuintic, QuinticSpline, Gaussian

from pysph.sph.equation import Group
from pysph.sph.basic_equations import ContinuityEquation, XSPHCorrection
from pysph.sph.wc.basic import TaitEOS, MomentumEquation

from pysph.solver.application import Application
from pysph.solver.solver import Solver
from pysph.sph.integrator import Integrator, WCSPHStep

dim = 3

dt = 1e-5
tf = 6.0

# parameter to chane the resolution
dx = 0.02
nboundary_layers=3
hdx = 1.2
ro = 1000.0

# the geometry generator
geom = DamBreak3DGeometry(
    dx=dx, nboundary_layers=nboundary_layers, hdx=hdx, rho0=ro)

h0 = dx * hdx
co = 10.0 * geom.get_max_speed(g=9.81)

gamma = 7.0
alpha = 0.5
beta = 0.0
B = co*co*ro/gamma

# Create the application.
app = Application()

# Create the kernel
kernel = WendlandQuintic(dim=dim)

# Create the integrator.
integrator = Integrator(fluid=WCSPHStep(),
                        boundary=WCSPHStep(),
                        obstacle=WCSPHStep())

# Create a solver.
solver = Solver(kernel=kernel, dim=dim, integrator=integrator)

# Setup default parameters.
solver.set_time_step(dt)
solver.set_final_time(tf)

# create the equations
equations = [

    # Equation of state
    Group(equations=[

            TaitEOS(dest='fluid', sources=None, rho0=ro, c0=co, gamma=gamma),
            TaitEOS(dest='boundary', sources=None, rho0=ro, c0=co, gamma=gamma),
            TaitEOS(dest='obstacle', sources=None, rho0=ro, c0=co, gamma=gamma),

            ]),

    # Continuity, momentum and xsph equations
    Group(equations=[

            ContinuityEquation(dest='fluid', sources=['fluid', 'boundary', 'obstacle']),
            ContinuityEquation(dest='boundary', sources=['fluid']),
            ContinuityEquation(dest='obstacle', sources=['fluid']),

            MomentumEquation(dest='fluid', sources=['fluid', 'boundary', 'obstacle'],
                             alpha=alpha, beta=beta, gz=-9.81, c0=co),

            XSPHCorrection(dest='fluid', sources=['fluid'])

            ]),
    ]

# Setup the application and solver.  This also generates the particles.
app.setup(solver=solver, equations=equations,
          particle_factory=geom.create_particles, hdx=hdx)

app.run()