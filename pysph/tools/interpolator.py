
import numpy as np
from pysph.base.utils import get_particle_array

from pysph.base.kernels import CubicSpline
from pysph.base.nnps import LinkedListNNPS as NNPS
from pysph.sph.equation import Equation
from pysph.sph.sph_eval import SPHEval

class InterpolateFunction(Equation):
    def initialize(self, d_idx, d_prop, d_number_density):
        d_prop[d_idx] = 0.0
        d_number_density[d_idx] = 0.0

    def loop(self, s_idx, d_idx, s_temp_prop, d_prop, d_number_density, WIJ):
        d_number_density[d_idx] += WIJ
        d_prop[d_idx] += WIJ*s_temp_prop[s_idx]

    def post_loop(self, d_idx, d_prop, d_number_density):
        if d_number_density[d_idx] > 1e-12:
            d_prop[d_idx] /= d_number_density[d_idx]


def get_bounding_box(particle_arrays, tight=False, stretch=0.05):
    """Find the size of the domain given a sequence of particle arrays.

    If `tight` is True, the bounds are tight, if not the domain is stretched
    along each dimension by an amount `stretch` specified as a percentage of
    the length along that dimension is added in each dimension.

    """
    xmin, xmax = 1e20, -1e20
    ymin, ymax = 1e20, -1e20
    zmin, zmax = 1e20, -1e20
    for pa in particle_arrays:
        x, y, z = pa.x, pa.y, pa.z
        xmin = min(xmin, x.min())
        xmax = max(xmax, x.max())
        ymin = min(ymin, y.min())
        ymax = max(ymax, y.max())
        zmin = min(zmin, z.min())
        zmax = max(zmax, z.max())

    bounds = np.asarray((xmin, xmax, ymin, ymax, zmin, zmax))
    if not tight:
        # Add the extra space.
        lengths = stretch*np.repeat(bounds[1::2] - bounds[::2], 2)
        lengths[::2] *= -1.0
        bounds += lengths

    return bounds

def get_nx_ny_nz(num_points, bounds):
    """Given a number of points to use and the bounds, return a triplet
    of integers for a uniform mesh with approximately that many points.
    """
    bounds = np.asarray(bounds, dtype=float)
    length = bounds[1::2] - bounds[::2]
    total_length = length.sum()
    rel_length = length/total_length
    non_zero = rel_length > 1e-3
    dim = int(non_zero.sum())
    volume = np.prod(length[non_zero])
    delta = pow(volume/num_points, 1.0/dim)
    dimensions = np.ones(3, dtype=int)
    for i in range(3):
        if rel_length[i] > 1e-4:
            dimensions[i] = int(round(length[i]/delta))

    return dimensions


class Interpolator(object):
    """Convenient class to interpolate particle properties onto a uniform
    grid.  This is particularly handy for visualization.
    """

    def __init__(self, particle_arrays, num_points=125000, kernel=None):
        """
        Parameters
        ----------

        particle_arrays: A list of particle arrays.
        num_points: the number of points to interpolate on to.
        kernel: the kernel to use for interpolation.
        """
        self._set_particle_arrays(particle_arrays)
        bounds = get_bounding_box(self.particle_arrays)
        shape = get_nx_ny_nz(num_points, bounds)
        self.dim = 3 - list(shape).count(1)

        if kernel is None:
            self.kernel = CubicSpline(dim=self.dim)
        else:
            self.kernel = kernel

        self.pa = None
        self.nnps = None
        self.func_eval = None
        self.set_domain(bounds, shape)

    #### Interpolator protocol ################################################
    def set_domain(self, bounds, shape):
        """Set the domain to interpolate into.

        Parameters:
        -------------

        bounds: (xmin, xmax, ymin, ymax, zmin, zmax)
        shape: (nx, ny, nz)
        """
        self.bounds = np.asarray(bounds)
        self.shape = np.asarray(shape)
        self.pa = self._create_particle_array()
        arrays = self.particle_arrays + [self.pa]

        if self.func_eval is None:
            self._create_sph_eval(arrays)

        self.update_particle_arrays(self.particle_arrays)

    def interpolate(self, prop, gradient=False):
        """

        :prop: The name of the property to interpolate.

        :gradient: bool: Evaluate gradient and not function.

        :return: A numpy array suitably shaped with the property
        interpolated.
        """
        for array in self.particle_arrays:
            data = array.get(prop)
            array.get('temp_prop')[:] = data

        self.func_eval.compute(0.0, 0.1) # These are junk arguments.
        result = self.pa.prop.copy()
        result.shape = self.shape
        return result.squeeze()

    def update_particle_arrays(self, particle_arrays):
        """Call this for a new set of particle arrays which have the
        same properties as before.

        For example, if you are reading the particle array data from files,
        each time you load a new file a new particle array is read with the
        same properties.  Call this function to reset the arrays.
        """
        self._set_particle_arrays(particle_arrays)
        arrays = self.particle_arrays + [self.pa]
        self._create_nnps(arrays)
        self.func_eval.update_particle_arrays(arrays)

    #### Private protocol #####################################################

    def _create_nnps(self, arrays):
        # create the neighbor locator object
        self.nnps = NNPS(dim=self.kernel.dim, particles=arrays,
                         radius_scale=self.kernel.radius_scale)
        self.nnps.update()
        self.func_eval.set_nnps(self.nnps)

    def _create_particle_array(self):
        b = self.bounds
        n = self.shape
        x, y, z = np.mgrid[b[0]:b[1]:n[0]*1j,
                           b[2]:b[3]:n[1]*1j,
                           b[4]:b[5]:n[2]*1j,
                          ]
        xr = x.ravel()
        yr = y.ravel()
        zr = z.ravel()
        self.x, self.y, self.z = x.squeeze(), y.squeeze(), z.squeeze()

        hmax = self._get_max_h_in_arrays()
        h = hmax*np.ones_like(xr)
        prop = np.zeros_like(xr)
        pa = get_particle_array(
            name='interpolate',
            x=xr, y=yr, z=zr, h=h,
            number_density=np.zeros_like(xr),
            prop=prop,
            grad_x=np.zeros_like(xr),
            grad_y=np.zeros_like(xr),
            grad_z=np.zeros_like(xr)
        )
        return pa

    def _create_sph_eval(self, arrays):
        names = [x.name for x in self.particle_arrays]
        equations = [InterpolateFunction(dest='interpolate', sources=names)]
        self.func_eval = SPHEval(
            arrays, equations, self.kernel, integrator=None
        )

    def _get_max_h_in_arrays(self):
        hmax = -1.0
        for array in self.particle_arrays:
            hmax = max(array.h.max(), hmax)
        return hmax

    def _set_particle_arrays(self, particle_arrays):
        self.particle_arrays = particle_arrays
        for array in self.particle_arrays:
            if 'temp_prop' not in array.properties:
                array.add_property('temp_prop')


def main(fname, prop, npoint):
    from pysph.solver.utils import load
    print "Loading", fname
    data = load(fname)
    arrays = data['arrays'].values()
    interp = Interpolator(arrays, num_points=npoint)
    print interp.shape
    print "Interpolating"
    prop = interp.interpolate(prop)
    print "Visualizing"
    from mayavi import mlab
    src = mlab.pipeline.scalar_field(interp.x, interp.y, interp.z, prop)
    if interp.dim == 3:
        mlab.pipeline.scalar_cut_plane(src)
    else:
        mlab.pipeline.surface(src)
    mlab.pipeline.outline(src)
    mlab.show()

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 4:
        print "Usage: interpolator.py filename property num_points"
        sys.exit(1)
    else:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]))