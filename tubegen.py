"""
Generator for carbon nano tubes.
"""

from math import gcd
import itertools
import argparse
import textwrap

import numpy as np

import lattice

def _define_parser():
    "Define command line argument parser for TubeGen."

    parser = argparse.ArgumentParser(prog="latgraph --generate tube",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent("""\
                Generate a carbon nano tube of given chirality and length.
                                     
                Boundary conditions may be (default: periodic)
                    - o / open
                    - p / periodic
                                     """))
    parser.add_argument("chirality", type=lambda s: tuple(map(int, s.split(","))),
                        help="Chirality of the tube, specify as n,m")
    parser.add_argument("length", type=int, help="Number of unit cells in the tube")
    parser.add_argument("--bc_ch", default="periodic",
                        help="Boundary condition along the circumference")
    parser.add_argument("--bc_t", default="periodic",
                        help="Boundary condition alogn the tube")
    parser.add_argument("--emb", default="3d", help="Embedding, can be 2d or 3d")
    parser.add_argument("--spacing", type=float, default="1", help="Lattice spacing")
    parser.add_argument("--name", default="", help="Name for the lattice")
    parser.add_argument("--comment", default="", help="Comment on the lattice")
    return parser

def _parse_args(in_args):
    "parse command line arguments for TubeGen."

    parser = _define_parser()
    args = parser.parse_args(in_args)

    # normalize and check arguments
    args.emb = args.emb.lower()
    if args.emb not in ("2d", "3d"):
        parser.error("Unknown embedding: {}".format(args.emb))

    args.bc_ch = args.bc_ch.lower()
    if args.bc_ch == "p":
        args.bc_ch = "periodic"
    elif args.bc_ch == "o":
        args.bc_ch = "open"
    if args.bc_ch not in ("periodic", "open"):
        parser.error("Unknown boundary condition for bc_ch: {}".format(args.bc_ch))

    args.bc_t = args.bc_t.lower()
    if args.bc_t == "p":
        args.bc_t = "periodic"
    elif args.bc_t == "o":
        args.bc_t = "open"
    if args.bc_t not in ("periodic", "open"):
        parser.error("Unknown boundary condition for bc_t: {}".format(args.bc_t))

    return args

def run(in_args):
    "Run TubeGen from command line arguments."

    args = _parse_args(in_args)
    gen = TubeGen(args.chirality, args.spacing)

    lat = gen.make_ribbon(args.length, args.bc_ch, args.bc_t)
    if args.emb == "3d":
        lat = gen.roll_tube(lat)

    if args.name:
        lat.name = args.name
    if args.comment:
        lat.comment = args.comment

    return lat

class TubeGen:
    """
    Generator for carbon nano tubes.

    Generates tubes of arbitrary chirality and computes 2D or 3D embedding.
    See Physical Properties Of Carbon Nanotubes
         - Dresselhaus G,Dresselhaus Mildred S,Saito
    for definitions of symbols / names used here.

    The chirality is specified as a tuple `(n, m)` in the constructor along
    with the lattice spacing. Then a ribbon or tube can be generated by
      - Ribbon: Call TubeGen.make_ribbon() and pass desired number of unit cells
                and boundary conditions in Ch and T directions.
                Keep in mind that the size of the ribbon is specified as if it were
                an unrolled tube, i.e. a unit cell can be more than a single hexagon.
      - Tube: First create a ribbon and then call TubeGen.roll_tube().

    Supported boundary conditions are "periodic" and "open". They can be specified
    for Ch and T directions speparately via bc_ch and bc_t, respectively.
    """

    def __init__(self, chirality, spacing):
        self.chirality = chirality
        self.spacing = spacing

    def n_hex_ucell(self):
        "Return number of hexagons per unit cell."
        n, m = self.chirality
        return 2*(m*m + n*n + m*n)//gcd(2*m+n, 2*n+m)

    def n_atoms_ucell(self):
        "Return number of atoms per unit cell."
        return 2*self.n_hex_ucell()

    def circumference(self):
        "Return circumference of tube."
        return np.linalg.norm(self.chiral_vector())

    def diameter(self):
        "Return dimater of tube."
        return self.circumference()/np.pi

    def unit_vectors(self):
        "Return the two unit vectors in the plane."
        return np.array([3/2, np.sqrt(3)/2])*self.spacing, \
            np.array([3/2, -np.sqrt(3)/2])*self.spacing

    def chiral_vector(self):
        "Return the chiral vector Ch in the physical basis."
        a1, a2 = self.unit_vectors()
        return self.chirality[0]*a1 + self.chirality[1]*a2

    def translation_vector_lat_basis(self):
        """
        Return the translation vector T in the lattice basis.
        (TubeGen.unit_vectors() are basis vectors.)
        """
        n, m = self.chirality
        dR = gcd(2*m+n, 2*n+m)
        return np.array(((2*m+n)/dR, -(2*n+m)/dR))

    def translation_vector(self):
        "Return the translation vector T in the physical basis."
        a1, a2 = self.unit_vectors()
        t1, t2 = self.translation_vector_lat_basis()
        return t1*a1 + t2*a2

    def symmetry_vector(self):
        "Return the symmetry vector R in the physical basis."

        a1, a2 = self.unit_vectors()
        t1, t2 = self.translation_vector_lat_basis()

        # require t1*q - t2*p = 1
        # and find smallest p that fulfills this equation for integer p, q
        for p in range(1, self.n_atoms_ucell()+1):
            q = (1 + p*t2)/t1
            if np.abs(q%1.) < 1e-10:  # q close to integer
                return p*a1 + q*a2

        raise RuntimeError("Unable to find symmetry vector")

    def make_ribbon(self, n_ucells, bc_ch, bc_t):
        """
        Create a 2D nano ribbon with given number of unit cells and boundary conditions.
        """

        T = self.translation_vector()

        # make a unit cell
        ucell = self._make_ucell()

        # replicate unit cell along T
        ribbon = lattice.Lattice(name="Ribbon ({}, {})".format(*self.chirality))
        for i in range(n_ucells):
            shifted = lattice.shifted_lattice(ucell, i*T)
            for site in shifted:
                site.idx += i*len(ucell)
            ribbon.sites.extend(shifted)

        # combine cells and handle boundary conditions
        _sow_cells(ribbon.sites, n_ucells, len(ucell), bc_ch, bc_t)
        return ribbon

    def roll_tube(self, ribbon):
        """
        Roll a 2D ribbon into a 3D nanotube.
        Rolls along the chiral vector Ch. The translation vector T
        becomes the direction of the tube.
        """

        Ch = self.chiral_vector()
        ch = np.linalg.norm(Ch)
        uCh = Ch / ch

        T = self.translation_vector()
        t = np.linalg.norm(T)
        uT = T / t

        radius = self.diameter()/2
        # turns 2D ribbon coordinate in Ch-direction into an angle
        angle_conversion = 2*np.pi/np.linalg.norm(self.chiral_vector())
        tube = lattice.Lattice(name="Tube ({}, {})".format(*self.chirality))
        for site in ribbon:
            # zylinder coordinates
            phi = angle_conversion*np.dot(site.pos, uCh)
            z = np.dot(site.pos, uT)
            tube.sites.append(lattice.Site(site.idx,
                                           np.array((radius*np.cos(phi),
                                                     radius*np.sin(phi),
                                                     z)),
                                           site.neighbours,
                                           site.hopping))
        return tube

    def __str__(self):
        "Return string showing basic properties of this tube."
        a1, a2 = self.unit_vectors()
        Ch = self.chiral_vector()
        T = self.translation_vector()
        R = self.symmetry_vector()

        return """## TubeGen ##
Chirality:           ({ch1}, {ch2})
Hexes per unit cell: {nhpuc}
Atoms per unit cell: {napuc}
Circumference:       {circ}
Diameter:            {diam}
Unit vectors:        ({uv11}, {uv12}), ({uv21}, {uv22})
Chiral vector:       ({cv1}, {cv2})
Translation Vector:  ({tv1}, {tv2})
Symmetry Vector:     ({sv1}, {sv2})""".format(
    ch1=self.chirality[0], ch2=self.chirality[1],
    nhpuc=self.n_hex_ucell(),
    napuc=self.n_atoms_ucell(),
    circ=self.circumference(),
    diam=self.diameter(),
    uv11=a1[0], uv12=a1[1], uv21=a2[0], uv22=a2[1],
    cv1=Ch[0], cv2=Ch[1],
    tv1=T[0], tv2=T[1],
    sv1=R[0], sv2=R[1]
)
    
    def _padded_lattice(self, lat):
        """
        Pad a given lattice by surrounding it with copies of the input.
        The input must be a 2D lattice.

        All site attributes are preserved in the copies. Only the positions are updated
        additional attributes called 'pad_ch' and 'pad_t' are added to all sites.
        For the centre lattice, they are each 0.
        For the surrounding lattices, they are 0 or +-1 depending on whether the lattice
        is translated in Ch or T direction with respect to the centre.
        """

        Ch = self.chiral_vector()
        T = self.translation_vector()

        padded = lattice.Lattice()
        for pad_ch, pad_t in itertools.product((0, +1, -1), repeat=2):
            aux = lattice.shifted_lattice(lat, pad_ch*Ch + pad_t*T)
            aux["pad_ch"] = pad_ch
            aux["pad_t"] = pad_t
            padded.sites.extend(aux)

        return padded

    def _connect_sites(self, lat):
        """
        Connects nearest neighbours in given 2D lattice (in-place).
        Uses fully periodic boundary conditions.
        Hopping strenghts are set to 1.

        All sites are given extra attributes called 'cross_ch_boudnary' and
        'cross_t_boundary' that are lists which indicate whether a nearest neighbour
        connection crosses the Ch or T boundary (values are 0, +1, -1).
        """

        # this way, we don't have to think about boundaries at all
        padded = self._padded_lattice(lat)

        # three shifts that get us from one site to all of its nearest neighbours
        # sign is sensitive to 'even-ness' of site (see below)
        a1, a2 = self.unit_vectors()
        shift0 = 1/3 * (a1 + a2)
        shift1 = shift0 - a1
        shift2 = shift0 - a2

        for site in lat:
            neighbours = []
            cross_ch_boundary = []
            cross_t_boundary = []

            for shift in (shift0, shift1, shift2):
                # get position of neighbour
                # lattice looks mirrored for odd sites w.r.t. even sites => different sign
                if site["even"]:
                    shifted = site.pos+shift
                else:
                    shifted = site.pos-shift

                neighbour = padded.at(shifted)
                if neighbour: # there might be no site there
                    neighbours.append(neighbour.idx)
                    cross_ch_boundary.append(neighbour["pad_ch"])
                    cross_t_boundary.append(neighbour["pad_t"])

            # store everything for this site
            site.neighbours = neighbours
            site.hopping = [1]*len(neighbours)
            site["cross_ch_boundary"] = cross_ch_boundary
            site["cross_t_boundary"] = cross_t_boundary

    def _make_ucell(self):
        """
        Create a single unit cell for a tube.
        All nearest neighbours in the cell are connected with periodic boundary conditions.

        Sites are placed at integer multiples of the symmetry vector R.
        i*R is projected onto Ch and T and the modulo is taken to make sure it
        stays within the unit cell. See psi and tau below.
        """

        Ch = self.chiral_vector()
        ch = np.linalg.norm(Ch)
        uCh = Ch / ch

        T = self.translation_vector()
        t = np.linalg.norm(T)
        uT = T / t

        R = self.symmetry_vector()

        a1, a2 = self.unit_vectors()
        eo_shift = 1/3 * (a1 + a2) # vector to get from an even site to one of its odd neighbours

        ucell = lattice.Lattice()
        idx = 0
        for i in range(self.n_atoms_ucell()//2):
            # even
            psi = np.dot(i*R, uCh) % ch
            tau = np.dot(i*R, uT) % t
            ucell.sites.append(lattice.Site(idx, psi*uCh + tau*uT, even=True))
            idx += 1

            # odd
            psi = np.dot(i*R + eo_shift, uCh) % ch
            tau = np.dot(i*R + eo_shift, uT) % t
            ucell.sites.append(lattice.Site(idx, psi*uCh + tau*uT, even=False))
            idx += 1

        self._connect_sites(ucell)
        return ucell


def _sow_cells(sites, n_ucells, luc, bc_ch, bc_t):
    """
    Connect nearest neighbours in given list of sites.
    'Sows' neighbouring unit cells together.
    Resolves boundary conditions both in Ch and T directions.

    Arguments:
        - sites: List of Sites, input and output
        - n_ucells: Number of unit cells in sites.
        - luc: Number of sites per unit cell.
        - bc_ch: Boundary condition in Ch direction.
        - bc_t: Boundary condition in T direction.
    """

    for i in range(n_ucells):
        for site in sites[i*luc:(i+1)*luc]:
            neighbours = []
            for neigh, xchb, xtb in zip(site.neighbours,
                                        site["cross_ch_boundary"],
                                        site["cross_t_boundary"]):
                # keep connection iff not across Ch boundary or periodic BC
                if xchb == 0 or bc_ch == "periodic":
                    if xtb == 0:
                        neighbours.append(neigh + i*luc)

                    elif xtb == 1 and (bc_t == "periodic" or i != n_ucells-1):
                        neighbours.append(neigh + (i+1)%n_ucells*luc)

                    elif xtb == -1 and (bc_t == "periodic" or i != 0):
                        neighbours.append(neigh + (i-1)%n_ucells*luc)

            site.neighbours = neighbours
