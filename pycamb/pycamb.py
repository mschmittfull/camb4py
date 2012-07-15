"""

A Python wrapper for CAMB

Example ::

    import pycamb
    camb = pycamb.pycamb('/path/to/camb')
    camb(get_scalar_cls='T')


Details
-------

This wrapper works ultra-fast by creating FIFO named pipes for 
the CAMB parameter file and output files, then calling CAMB 
which subsequenty reads/writes to these pipes. This means everything
is stored in memory the whole time there is zero disk I/O. 
The only "wasted" time is spent translating the outputs to/from text, 
however I calculate this is maximum about ###ms per call. 
This also has the huge advantage that it lets one use any 
existing CAMB executable without modification on the fly.

"""

import os, re, subprocess
from ConfigParser import RawConfigParser
from StringIO import StringIO
from tempfile import mktemp
from threading import Thread, Event
from numpy import loadtxt


class pycamb(object):
    
    def __init__(self, executable, defaults=None):
        """
        
        Prepare a CAMB executable to be called from Python.
        
        Parameters
        ----------
        executable : path to the CAMB executable
        defaults : string or a filename containing a default ini file
                   to be used for parameters which aren't specified 
                   (default: see pycamb._defaults)
        
        Returns
        -------
        pycamb object which can be called with a list of parameters
        
        """
        self.defaults = _read_ini(defaults or _defaults)
        if not os.path.exists(executable): raise Exception("Couldn't find CAMB executable '%s'"%executable)
        else: self.executable = os.path.abspath(executable)
    
    
    def __call__(self, **params):
        """
        
        Call CAMB and return the output files as well as std-out. 
        
        Parameters
        ----------
        
        **params : all key value pairs are passed to the CAMB ini
        
        """
        p = self.defaults.copy()
        p.update(params)
        for k in _output_files: p.pop(k,None)
            
        outputfiles = []
        if p['get_scalar_cls']=='T': outputfiles += ['scalar_output_file']
        if p['get_vector_cls']=='T': outputfiles += ['vector_output_file']
        if p['get_tensor_cls']=='T': outputfiles += ['tensor_output_file']
        if p['do_lensing']=='T': outputfiles += ['lensed_output_file', 'lensed_output_file']
        if p['get_transfer']=='T': outputfiles += ['transfer_filename(1)', 'transfer_matterpower(1)']

        for k in outputfiles: 
            p[k]=mktemp(suffix='_%s'%k)
            os.mkfifo(p[k])
            
        paramfile = mktemp(suffix='_param')
        os.mkfifo(paramfile)
        
        result = {}
        
        def writeparams():
            with open(paramfile,'w') as f: 
                f.write('\n'.join(['%s = %s'%i for i in p.items()]+['END','']))
        
        def readoutputs(readany):
            ro_started.set()
            for k in outputfiles:
                with open(p[k]) as f:
                    read_any[0]=True
                    try: result[_output_files[k]] = loadtxt(f)
                    except Exception: pass

        wp_thread = Thread(target=writeparams)
        wp_thread.start()
        
        read_any = [False]
        ro_started = Event()
        ro_thread = Thread(target=readoutputs,args=(read_any,))
        ro_thread.start()
        ro_started.wait()
        
        
        result['stdout'] = subprocess.check_output(['./%s'%os.path.basename(self.executable),paramfile],
                                                   cwd=os.path.dirname(self.executable))
        
        if read_any[0]:  
            ro_thread.join()
        else:
            for k in outputfiles: open(p[k],'a').close()
        
        for k in outputfiles: os.unlink(p[k])
        os.unlink(paramfile)

        return result
    05
    def derivative(self, dparam, params, delta=None):
        """Get a derivative."""
        params[dparam] += delta/2
        d1 = self(**params)
        params[dparam] -= delta
        d0 = self(**params)
        
        for k,v in d1.items():
            if k!='stdout': v[:,1:] = (v[:,1:] - d0[k][:,1:])/delta
        
        d1['stdout'] = (d0['stdout'],d1['stdout'])
        return d1
        
    
def _get_params(self, sourcedir):
    """Scour CAMB source files for valid parameters"""
    camb_keys=set()
    for f in os.listdir('.'):
        if f.endswith('90'):
            with open(f) as f:
                for line in f:
                    r = re.search("Ini_Read.*File\(.*?,'(.*)'",line,re.IGNORECASE)
                    if r: camb_keys.add(r.group(1))
                    r = re.search("Ini_Read.*\('(.*)'",line,re.IGNORECASE)
                    if r: camb_keys.add(r.group(1))    
                    
    return camb_keys

    
    
def _read_ini(ini):
    """Load an ini file or string into a dictionary."""
    if os.path.exists(ini): ini = open(ini).read()
    config = RawConfigParser()
    config.readfp(StringIO('[root]\n'+ini))
    return dict(config.items('root'))
        


_output_files = {'scalar_output_file':'scalar',
                 'vector_output_file':'vector',
                 'tensor_output_file':'tensor',
                 'total_output_file:':None,
                 'lensed_output_file':'lensed', 
                 'lens_potential_output_file':'lens_potential',
                 'lensed_total_output_file':None,
                 'transfer_filename(1)':'transfer',
                 'transfer_matterpower(1)':'transfer_matterpower'}



_defaults="""
#Parameters for CAMB

#output_root is prefixed to output file names
output_root = 

#What to do
get_scalar_cls = F
get_vector_cls = F
get_tensor_cls = F
get_transfer   = F

#if do_lensing then scalar_output_file contains additional columns of l^4 C_l^{pp} and l^3 C_l^{pT}
#where p is the projected potential. Output lensed CMB Cls (without tensors) are in lensed_output_file below.
do_lensing     = F

# 0: linear, 1: non-linear matter power (HALOFIT), 2: non-linear CMB lensing (HALOFIT)
do_nonlinear = 0

#Maximum multipole and k*eta. 
#  Note that C_ls near l_max are inaccurate (about 5%), go to 50 more than you need
#  Lensed power spectra are computed to l_max_scalar-100 
#  To get accurate lensed BB need to have l_max_scalar>2000, k_eta_max_scalar > 10000
#  Otherwise k_eta_max_scalar=2*l_max_scalar usually suffices, or dont set to use default
l_max_scalar      = 2200
#k_eta_max_scalar  = 4000

#  Tensor settings should be less than or equal to the above
l_max_tensor      = 1500
k_eta_max_tensor  = 3000

#Main cosmological parameters, neutrino masses are assumed degenerate
# If use_phyical set phyiscal densities in baryone, CDM and neutrinos + Omega_k
use_physical   = T
ombh2          = 0.0226
omch2          = 0.112
omnuh2         = 0
omk            = 0
hubble         = 70
#effective equation of state parameter for dark energy, assumed constant
w              = -1
#constant comoving sound speed of the dark energy (1=quintessence)
cs2_lam        = 1

#if use_physical = F set parameters as here
#omega_baryon   = 0.0462
#omega_cdm      = 0.2538
#omega_lambda   = 0.7
#omega_neutrino = 0

temp_cmb           = 2.726
helium_fraction    = 0.24
# massless_neutrinos is the effective number (for QED + non-instantaneous decoupling)
# fractional part of the number is used to increase the neutrino temperature, e.g.
# 2.99 correponds to 2 neutrinos with a much higher temperature, 3.04 correponds to
# 3 neutrinos with a slightly higher temperature. 3.046 is consistent with CosmoMC.
massless_neutrinos = 0.04
massive_neutrinos  = 3

#Neutrino mass splittings
nu_mass_eigenstates = 1
#nu_mass_degeneracies = 0 sets nu_mass_degeneracies = massive_neutrinos
#otherwise should be an array
#e.g. for 3 neutrinos with 2 non-degenerate eigenstates, nu_mass_degeneracies = 2 1
nu_mass_degeneracies = 0  
#Fraction of total omega_nu h^2 accounted for by each eigenstate, eg. 0.5 0.5
nu_mass_fractions = 1

#Initial power spectrum, amplitude, spectral index and running. Pivot k in Mpc^{-1}.
initial_power_num         = 1
pivot_scalar              = 0.05
pivot_tensor              = 0.05
scalar_amp(1)             = 2.1e-9
scalar_spectral_index(1)  = 0.96
scalar_nrun(1)            = 0
tensor_spectral_index(1)  = 0
#ratio is that of the initial tens/scal power spectrum amplitudes
initial_ratio(1)          = 1
#note vector modes use the scalar settings above


#Reionization, ignored unless reionization = T, re_redshift measures where x_e=0.5
reionization         = T

re_use_optical_depth = T
re_optical_depth     = 0.09
#If re_use_optical_depth = F then use following, otherwise ignored
re_redshift          = 11
#width of reionization transition. CMBFAST model was similar to re_delta_redshift~0.5.
re_delta_redshift    = 1.5
#re_ionization_frac=-1 sets to become fully ionized using YHe to get helium contribution
#Otherwise x_e varies from 0 to re_ionization_frac
re_ionization_frac   = -1


#RECFAST 1.5 recombination parameters;
RECFAST_fudge = 1.14
RECFAST_fudge_He = 0.86
RECFAST_Heswitch = 6
RECFAST_Hswitch  = T

#Initial scalar perturbation mode (adiabatic=1, CDM iso=2, Baryon iso=3, 
# neutrino density iso =4, neutrino velocity iso = 5) 
initial_condition   = 1
#If above is zero, use modes in the following (totally correlated) proportions
#Note: we assume all modes have the same initial power spectrum
initial_vector = -1 0 0 0 0

#For vector modes: 0 for regular (neutrino vorticity mode), 1 for magnetic
vector_mode = 0

#Normalization
COBE_normalize = F
##CMB_outputscale scales the output Cls
#To get MuK^2 set realistic initial amplitude (e.g. scalar_amp(1) = 2.3e-9 above) and
#otherwise for dimensionless transfer functions set scalar_amp(1)=1 and use
#CMB_outputscale = 1
CMB_outputscale = 7.4311e12

#Transfer function settings, transfer_kmax=0.5 is enough for sigma_8
#transfer_k_per_logint=0 sets sensible non-even sampling; 
#transfer_k_per_logint=5 samples fixed spacing in log-k
#transfer_interp_matterpower =T produces matter power in regular interpolated grid in log k; 
# use transfer_interp_matterpower =F to output calculated values (e.g. for later interpolation)
transfer_high_precision = F
transfer_kmax           = 2
transfer_k_per_logint   = 0
transfer_num_redshifts  = 1
transfer_interp_matterpower = T
transfer_redshift(1)    = 0
transfer_filename(1)    = transfer_out.dat
#Matter power spectrum output against k/h in units of h^{-3} Mpc^3
transfer_matterpower(1) = matterpower.dat


#Output files not produced if blank. make camb_fits to use use the FITS setting.
scalar_output_file = scalCls.dat
vector_output_file = vecCls.dat
tensor_output_file = tensCls.dat
total_output_file  = totCls.dat
lensed_output_file = lensedCls.dat
lensed_total_output_file  =lensedtotCls.dat
lens_potential_output_file = lenspotentialCls.dat
FITS_filename      = scalCls.fits

#Bispectrum parameters if required; primordial is currently only local model (fnl=1)
#lensing is fairly quick, primordial takes several minutes on quad core
do_lensing_bispectrum = F
do_primordial_bispectrum = F

#1 for just temperature, 2 with E
bispectrum_nfields = 1
#set slice non-zero to output slice b_{bispectrum_slice_base_L L L+delta}
bispectrum_slice_base_L = 0
bispectrum_ndelta=3
bispectrum_delta(1)=0
bispectrum_delta(2)=2
bispectrum_delta(3)=4
#bispectrum_do_fisher estimates errors and correlations between bispectra
#note you need to compile with LAPACK and FISHER defined to use get the Fisher info
bispectrum_do_fisher= F
#Noise is in muK^2, e.g. 2e-4 roughly for Planck temperature
bispectrum_fisher_noise=0
bispectrum_fisher_noise_pol=0
bispectrum_fisher_fwhm_arcmin=7
#Filename if you want to write full reduced bispectrum (at sampled values of l_1)
bispectrum_full_output_file=
bispectrum_full_output_sparse=F
#Export alpha_l(r), beta_l(r) for local non-Gaussianity
bispectrum_export_alpha_beta=F

##Optional parameters to control the computation speed,accuracy and feedback

#If feedback_level > 0 print out useful information computed about the model
feedback_level = 1

# 1: curved correlation function, 2: flat correlation function, 3: inaccurate harmonic method
lensing_method = 1
accurate_BB = F


#massive_nu_approx: 0 - integrate distribution function
#                   1 - switch to series in velocity weight once non-relativistic
massive_nu_approx = 1

#Whether you are bothered about polarization. 
accurate_polarization   = T

#Whether you are bothered about percent accuracy on EE from reionization
accurate_reionization   = T

#whether or not to include neutrinos in the tensor evolution equations
do_tensor_neutrinos     = T

#Whether to turn off small-scale late time radiation hierarchies (save time,v. accurate)
do_late_rad_truncation   = T

#Computation parameters
#if number_of_threads=0 assigned automatically
number_of_threads       = 0

#Default scalar accuracy is about 0.3% (except lensed BB) if high_accuracy_default=F
#If high_accuracy_default=T the default taget accuracy is 0.1% at L>600 (with boost parameter=1 below)
#Try accuracy_boost=2, l_accuracy_boost=2 if you want to check stability/even higher accuracy
#Note increasing accuracy_boost parameters is very inefficient if you want higher accuracy,
#but high_accuracy_default is efficient 

high_accuracy_default=F

#Increase accuracy_boost to decrease time steps, use more k values,  etc.
#Decrease to speed up at cost of worse accuracy. Suggest 0.8 to 3.
accuracy_boost          = .8

#Larger to keep more terms in the hierarchy evolution. 
l_accuracy_boost        = 1

#Increase to use more C_l values for interpolation.
#Increasing a bit will improve the polarization accuracy at l up to 200 -
#interpolation errors may be up to 3%
#Decrease to speed up non-flat models a bit
l_sample_boost          = 1
"""