from __future__ import print_function
import numpy as np
import matplotlib.pyplot as plt
import pyfits
import glob
from simple_acf import simple_acf
from measure_GP_rotation import bin_data
import h5py
import time
from GProtation import lnprob
from multiprocessing import Pool


def load_kepler_data(fnames):
    hdulist = pyfits.open(fnames[0])
    t = hdulist[1].data
    time = t["TIME"]
    flux = t["PDCSAP_FLUX"]
    flux_err = t["PDCSAP_FLUX_ERR"]
    q = t["SAP_QUALITY"]
    m = np.isfinite(time) * np.isfinite(flux) * np.isfinite(flux_err) * \
            (q == 0)
    x = time[m]
    med = np.median(flux[m])
    y = flux[m]/med - 1
    yerr = flux_err[m]/med
    for fname in fnames[1:]:
       hdulist = pyfits.open(fname)
       t = hdulist[1].data
       time = t["TIME"]
       flux = t["PDCSAP_FLUX"]
       flux_err = t["PDCSAP_FLUX_ERR"]
       q = t["SAP_QUALITY"]
       m = np.isfinite(time) * np.isfinite(flux) * np.isfinite(flux_err) * \
               (q == 0)
       x = np.concatenate((x, time[m]))
       med = np.median(flux[m])
       y = np.concatenate((y, flux[m]/med - 1))
       yerr = np.concatenate((yerr, flux_err[m]/med))
    return x, y, yerr


def fit(x, y, yerr, id, p_init, plims, DIR, burnin=500, run=1500, npts=48,
        nwalkers=32, cutoff=1000, sine_kernel=True, runMCMC=True, plot=False):
    """
    takes x, y, yerr and initial guesses and priors for period and does the
    the GP MCMC.
    id: the kepler id
    p_init: period initial guess
    plims: tuple, upper and lower limit for the prior
    DIR: the directory to save the results
    npts: number of points per bin (48 for one bin per day)
    """
    if sine_kernel:
        print("sine kernel")
        theta_init = [np.exp(-5), np.exp(7), np.exp(.6), np.exp(-16), p_init]
        print("log theta init = ", np.log(theta_init))
        from GProtation import MCMC, make_plot
    else:
        print("cosine kernel")
        theta_init = [1e-2, 1., 1e-2, p_init]
        print("log theta init = ", np.log(theta_init))
        from GProtation_cosine import MCMC, make_plot

    xb, yb, yerrb = bin_data(x, y, yerr, npts) # bin data
    plt.clf()
    plt.plot(x, y, "k.")
    plt.plot(xb, yb, "r.")
    plt.xlim(220, 235)
    plt.savefig("data")
    assert 0
    m = cutoff  # truncate data
    xb, yb, yerrb = xb[:m], yb[:m], yerrb[:m]

    import george
    from george.kernels import ExpSquaredKernel, ExpSine2Kernel, WhiteKernel
    th = theta_init
    k = th[0] * ExpSquaredKernel(th[1]) * ExpSine2Kernel(th[2], th[4]) + \
            WhiteKernel(th[3])
    gp = george.GP(k)
    gp.compute(xb, yerrb)
    xs = np.linspace(min(xb), max(xb), 1000)
    mu, cov = gp.predict(yb, xs)
    plt.clf()
    plt.plot(xb, yb, "k.")
    plt.plot(xs, mu)
    plt.savefig("prediction_initial")

    gp.optimize(xb, yb, yerrb)
    mu, cov = gp.predict(yb, xs)
    plt.clf()
    plt.plot(xb, yb, "k.")
    plt.plot(xs, mu)
    plt.savefig("prediction_final")

    theta_init = np.log(theta_init)

    start = time.time()
    lnprob(theta_init, xb, yb, yerrb, plims)
    end = time.time()
    ti = end-start
    print("1 likelihood call takes", ti, "seconds")
    print((burnin * nwalkers * ti)/60, "minutes for burnin")
    print((run * nwalkers * ti)/60, "minutes for full run")

    if runMCMC:
        sampler = MCMC(theta_init, xb, yb, yerrb, plims, burnin, run,
                       id, DIR, nwalkers)

    # make various plots
    if plot:
        with h5py.File("{0}/{1}_samples.h5".format(DIR, str(int(id)).zfill(9)),
                       "r") as f:
            samples = f["samples"][...]
        mcmc_result = make_plot(samples, xb, yb, yerrb, id, DIR,
                                traces=True, tri=True, prediction=True)


def run_on_single_lc(id):
    """
    Runs GProtation code on a ensemble of kepler targets
    id: a kepler id (string)
    """

    # load the first light curve
    p = "/home/angusr/.kplr/data/lightcurves"
    path = "{0}/{1}/*llc.fits".format(p, str(int(id)).zfill(9))
    fnames = np.sort(glob.glob(path))

    x, y, yerr = load_kepler_data(fnames)

    plt.clf()
    plt.subplot(2, 1, 1)
    plt.plot(x, y, "k.")

    # calculate acf
    period, acf, lags = simple_acf(x, y)
    print("\n", "acf period = ", period, "days", "\n")

    plt.subplot(2, 1, 2)
    plt.axvline(period, color="r")
    plt.plot(lags, acf)
    plt.savefig(id)

    # run MCMC
    p_init = period
    plims = (np.log(period - .2*period), np.log(period + .2*period))
    DIR = "results"
    fit(x, y, yerr, id, p_init, plims, DIR, burnin=500, run=3000, npts=12,
        nwalkers=24, cutoff=500, plot=True)

if __name__ == "__main__":

    # load Kepler IDs
    data = np.genfromtxt("data/garcia.txt", skip_header=1).T
    kids = [str(int(i)).zfill(9) for i in data[0]]
    id = kids[1]
    run_on_single_lc(id)

#     pool = Pool()
#     results = pool.map(run_on_single_lc, kids)