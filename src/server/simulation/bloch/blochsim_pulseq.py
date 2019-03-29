import numpy as np
import matplotlib.pyplot as plt
import time
import bloch as blc
import phantom as pht
from pulseq.core.Sequence.sequence import Sequence
from pulseq.core.Sequence.read_seq import read
import multiprocessing as mp
import spingroup_ps as sg

GAMMA_BAR = 42.58e6
GAMMA = 2*42.58e6 * np.pi


def apply_pulseq(isc,seq):
    """
    Applies a pulseq Sequence onto a SpinGroup and returns magnetization signals

    INPUTS
    isc - SpinGroup object from spingroup_ps.py
    seq - pulseq Sequence object

    OUTPUTS
    signal - all ADC samples taken during application of seq
    """
    signal = []
    events = seq.block_events

    dt_grad = seq.system.grad_raster_time
    dt_rf = seq.system.rf_raster_time

    # Go through pulseq block by block and simulate
    for key in events.keys():
        event_row = events[key]
        this_blk = seq.get_block(key)

        # Case 1: Delay
        if event_row[0] != 0:
            delay = this_blk['delay'].delay[0]
            isc.delay(delay)

        # Case 2: RF pulse
        elif event_row[1] != 0:
            # Later: add ring down and dead time to be more accurate?
            b1 = this_blk['rf'].signal/GAMMA_BAR
            rf_time = np.array(this_blk['rf'].t[0]) - dt_rf
            rf_grad, rf_timing, rf_duration = combine_gradients(blk=this_blk, timing=rf_time)
            isc.apply_rf(b1,rf_grad,dt_rf)

        # Case 3: ADC sampling #TODO what's wrong?? dk is wrong - fix
        # TODO Add post-delay
        elif event_row[5] != 0:
            adc = this_blk['adc']
            signal_1D = []
            dt_adc = adc.dwell
            delay = adc.delay
            grad, timing, duration = combine_gradients(blk=this_blk, dt=dt_adc, delay=delay)
            isc.fpwg(grad[:,0]*delay,delay)
            v = 1
            for q in range(1,len(timing)):
                if v <= int(adc.num_samples):
                    signal_1D.append(isc.get_m_signal())
                isc.fpwg(grad[:,v]*dt_adc,dt_adc)
                v += 1
            signal.append(signal_1D)

        # Case 4: just gradients
        elif event_row[2] != 0 or event_row[3] != 0 or event_row[4] != 0:
            # Process gradients
            fp_grads_area = combine_gradient_areas(blk=this_blk)
            dur = find_precessing_time(blk=this_blk,dt=dt_grad)
            isc.fpwg(fp_grads_area,dur)

    return signal


def sim_single_spingroup(loc_ind,freq_offset,phantom,seq):
    isc = sg.SpinGroup(loc=phantom.get_location(loc_ind), pdt1t2=phantom.get_params(loc_ind), df=freq_offset)
    signal = apply_pulseq(isc,seq)
    return signal



# Helpers
def combine_gradient_areas(blk):
    """
    Combines gradient areas in a pulseq Block
    INPUTS
    blk - pulseq Block obtained from seq.get_block()
    OUTPUT:
    Array [Ax, Ay, Az] - x, y, and z gradient areas. Units: [sec*T/m]
    """
    grad_areas = []
    for g_name in ['gx','gy','gz']:
        if blk.__contains__(g_name):
            g = blk[g_name]
            g_area = g.area if g.type == 'trap' else np.trapz(y=g.waveform, x=g.t)
            grad_areas.append(g_area)
        else:
            grad_areas.append(0)
    return np.array(grad_areas)/GAMMA_BAR


def combine_gradients(blk,dt=0,timing=(),delay=0):
    # Key method!
    """
    Interpolate x, y, and z gradients starting from time 0
    at dt intervals, for as long as the longest gradient lasts
    and combine them into a 3 x N array
    INPUTS:
    blk - pulseq Block obtained from seq.get_block()
    dt* - raster time used in interpolating gradients
    timing* - timing points at which gradients are interpolated
        *Note: only one option, dt or timing, is expected as input
    delay - if nonzero, this adds an additional interval = delay at the beginning of the interpolation
            Currently only used in ADC sampling to capture ADC delay
    """
    grad_timing = []
    duration = 0
    if dt != 0:
        duration = find_precessing_time(blk,dt)
        grad_timing = np.arange(0,duration,dt) if delay == 0 else np.concatenate(([0],np.arange(delay,duration,dt)))
    elif len(timing) != 0:
        duration = timing[-1] - timing[0]
        grad_timing = timing

    grad = []

    # Interpolate gradient values at desired time points
    for g_name in ['gx','gy','gz']:
        if blk.__contains__(g_name):
            g = blk[g_name]
            g_time, g_shape = ([0, g.rise_time, g.rise_time + g.flat_time, g.rise_time + g.flat_time + g.fall_time],
                               [0,g.amplitude/GAMMA_BAR,g.amplitude/GAMMA_BAR,0]) if g.type == 'trap'\
                               else (g.t, g.waveform/GAMMA_BAR)
            #if g_name == 'gz':
             #   print('g_time:',g_time)
              #  print('g_shape:',g_shape)
               # print('grad timing:',grad_timing)
                #print('interp result:',np.interp(x=grad_timing,xp=g_time,fp=g_shape))
            grad.append(np.interp(x=grad_timing,xp=g_time,fp=g_shape))
        else:
            grad.append(np.zeros(np.shape(grad_timing)))

    return np.array(grad), grad_timing, duration


def find_precessing_time(blk,dt):
    """
    Finds and returns longest duration among Gx, Gy, and Gz
        for use in SpinGroup.fpwg()
    INPUTS
    blk - pulseq Block obtained from seq.get_block()
    dt - gradient raster time for calculating duration of only arbitrary gradients ('grad' instead of 'trap')
    OUTPUT
    Maximum gradient time among the three gradients Gx, Gy, and Gz
    """
    grad_times = []
    for g_name in ['gx','gy','gz']:
        if blk.__contains__(g_name):
            g = blk[g_name]
            tg = (g.rise_time + g.flat_time + g.fall_time) if g.type == 'trap' else len(g.t[0])*dt
            grad_times.append(tg)
    return max(grad_times)



# Main program
# Parallel simulation
if __name__ == '__main__':
    # Create phantom
    Nph = 5
    #FOVph = 0.32
    FOVph = 32
    #Rs = [0.06, 0.12, 0.15]
    Rs = [6,12,15]
    PDs = [1, 1, 1]
    T1s = [2, 1, 0.5]
    T2s = [0.1, 0.15, 0.25]
    phantom = pht.makeSphericalPhantom(n=Nph, fov=FOVph, T1s=T1s, T2s=T2s, PDs=PDs, radii=Rs)
    df = 0

    # Tic
    start_time = time.time()

    # Load pulseq file
    myseq = Sequence()
#    myseq.read("gre_python_forsim_9.seq")
    myseq.read('irse_python_forsim_5_fov32_rev.seq')
    loc_ind_list = phantom.get_list_inds()
    pool = mp.Pool(mp.cpu_count())
    results = pool.starmap_async(sim_single_spingroup, [(loc_ind, df, phantom, myseq) for loc_ind in loc_ind_list]).get()
    pool.close()

    my_signal = np.sum(results,axis=0)

    # Toc
    print("Time used: %s seconds" % (time.time()-start_time))
    # Save signal
    np.save('pulseq_signal_new.npy', my_signal)
    # Display results
    ss = np.load('pulseq_signal_new.npy')
    plt.figure(1)
    plt.imshow(np.absolute(ss))
    plt.gray()

    aa = np.fft.fftshift(np.fft.ifft2(ss))
    plt.figure(2)
    plt.imshow(np.absolute(aa))
    plt.gray()
    plt.show()
