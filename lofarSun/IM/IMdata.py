from scipy.io import readsav
import matplotlib.dates as mdates
import matplotlib as mpl
import datetime
import glob
import os

from astropy import units as u
from astropy.coordinates import EarthLocation, SkyCoord
from astropy.io import fits
from astropy.time import Time

import numpy as np
from skimage import measure
from scipy.ndimage import gaussian_filter
import matplotlib.pyplot as plt
import cv2
import sunpy
import sunpy.map
import sunpy.coordinates.sun as sun_coord
from sunpy.coordinates.sun import sky_position as sun_position
from sunpy.coordinates import frames
import scipy
import scipy.ndimage
from matplotlib.patches import Ellipse

# try to use the precise epoch
mpl.rcParams['date.epoch']='1970-01-01T00:00:00'
try:
    mdates.set_epoch('1970-01-01T00:00:00')
except:
    pass


class IMdata:
    def __init__(self):
        self.havedata = False
        self.data=np.zeros(1)
        self.t_obs=np.zeros(1)
        self.freq=np.zeros(1)
        self.xx=np.zeros(1)
        self.yy=np.zeros(1)
        self.data_xy_calib=np.zeros(1)
        self.beamArea=np.zeros(1)
        self.fname=''
        
    def load_fits(self,fname):
        if len(fname)>0:
            self.havedata = True
            self.fname = fname
            hdulist = fits.open(fname)
            hdu = hdulist[0]
            self.header = hdu.header
            self.t_obs = sunpy.time.parse_time(self.header['DATE-OBS']).datetime
            self.freq = hdu.header['CRVAL3']/1e6
            data=np.zeros((hdu.header[3],hdu.header[4]), dtype=int)
            data = hdu.data
            self.data=data[0,0,:,:]
            [RA_sun,DEC_sun] = self.get_cur_solar_centroid(t_obs=self.t_obs)
            [RA_obs,DEC_obs] = self.get_obs_image_centroid(self.header)
            [RA_ax ,DEC_ax ] = self.get_axis_obs(self.header)

            [self.xx,self.yy] = self.RA_DEC_shift_xy0(RA_ax,DEC_ax,RA_obs,DEC_obs)
            self.data_xy = self.sun_coord_trasform(self.data,self.header,True,True)
            [b_maj,b_min,b_ang] = self.get_beam()
            self.beamArea = (b_maj/180*np.pi)*(b_min/180*np.pi)*np.pi /(4*np.log(2))
            self.data_xy_calib = self.data_xy*(300/self.freq)**2/2/(1.38e-23)/1e26/self.beamArea

    
    def get_cur_solar_centroid(self,t_obs):
            # use the observation time to get the solar center
        [RA,DEC] = sun_position(t=t_obs, equinox_of_date=False)
        return [RA.degree%360,DEC.degree%360]

    def get_obs_image_centroid(self,header):
        # get the RA DEC center of the image from the solar center
        RA_obs = header['CRVAL1']
        DEC_obs = header['CRVAL2']
        return [RA_obs%360,DEC_obs%360]

    def get_axis_obs(self,header):
        # make the header with the image
        # refer to https://www.atnf.csiro.au/computing/software/miriad/progguide/node33.html
        if self.havedata:
            [RA_c,DEC_c] = self.get_obs_image_centroid(self.header)
            RA_ax_obs   = RA_c + ((np.arange(header['NAXIS1'])+1) 
                                -header['CRPIX1'])*header['CDELT1']/np.cos((header['CRVAL2'])/180.*np.pi)
            DEC_ax_obs  = DEC_c+ ((np.arange(header['NAXIS2'])+1) 
                                -header['CRPIX2'])*header['CDELT2']
            return [RA_ax_obs,DEC_ax_obs]
        else:
            print("No data loaded")
            
    def RA_DEC_shift_xy0(self,RA,DEC,RA_cent,DEC_cent):
        # transformation between the observed coordinate and the solar x-y coordinate
        # including the x-y shift
        x_geo = -(RA  -  RA_cent)*np.cos(DEC_cent/180.*np.pi)*3600
        y_geo = -(DEC_cent - DEC)*3600
        # (in arcsec)
        # the rotation angle of the sun accoording to the date
        return [x_geo,y_geo]

    def sun_coord_trasform(self,data,header,act_r=True,act_s=True):
        # act_r : rotation operation
        # act_s : shift operation
        if self.havedata:
            [RA_sun,DEC_sun] = self.get_cur_solar_centroid(self.t_obs);
            [RA_obs,DEC_obs] = self.get_obs_image_centroid(header);
            x_shift_pix = (RA_sun  - RA_obs) /header['CDELT1']
            y_shift_pix = (DEC_sun - DEC_obs)/header['CDELT2']
            if act_s==False:
                x_shift_pix = 0
                y_shift_pix = 0
            rotate_angel = sun_coord.P(self.t_obs).degree
            if act_r==False:
                rotate_angel = 0
            data_tmp = scipy.ndimage.shift(data,(x_shift_pix,y_shift_pix))
            data_new = scipy.ndimage.rotate(data_tmp,rotate_angel,reshape=False)
            return data_new
        else:
            print("No data loaded")
                        
        
    def get_beam(self):
        if self.havedata:
            solar_PA = sun_coord.P(self.t_obs).degree
            b_maj =  self.header['BMAJ']
            b_min  = self.header['BMIN']
            b_ang = self.header['BPA']+solar_PA # should consider the beam for the data
            return [b_maj,b_min,b_ang]
        else:
            print("No data loaded")

    def make_map(self,fov=2500):
        # still in beta version, use with caution
        # ref : https://gist.github.com/hayesla/42596c72ab686171fe516f9ab43300e2
        hdu = fits.open(self.fname)
        header = hdu[0].header
        data_jybeam = np.squeeze(hdu[0].data)

        data = data_jybeam*(300/self.freq)**2/2/(1.38e-23)/1e26/self.beamArea
        # speed of light 3e8, MHz 1e6


        obstime = Time(header['date-obs'])
        frequency = header['crval3']*u.Hz
        reference_coord = SkyCoord(header['crval1']*u.deg, header['crval2']*u.deg,
                           frame='gcrs',
                           obstime=obstime,
                           distance=sun_coord.earth_distance(obstime),
                           equinox='J2000')
        lofar_loc = EarthLocation(lat=52.905329712*u.deg, lon=6.867996528*u.deg) # location of the center of LOFAR
        lofar_coord = SkyCoord(lofar_loc.get_itrs(Time(obstime)))
        reference_coord_arcsec = reference_coord.transform_to(frames.Helioprojective(observer=lofar_coord))
        cdelt1 = (np.abs(header['cdelt1'])*u.deg).to(u.arcsec)
        cdelt2 = (np.abs(header['cdelt2'])*u.deg).to(u.arcsec)
        P1 = sun_coord.P(obstime)
        new_header = sunpy.map.make_fitswcs_header(data, reference_coord_arcsec,
                                           reference_pixel=u.Quantity([header['crpix1']-1, header['crpix2']-1]*u.pixel),
                                           scale=u.Quantity([cdelt1, cdelt2]*u.arcsec/u.pix),
                                           rotation_angle=-P1,
                                           wavelength=frequency.to(u.MHz),
                                           observatory='LOFAR')
        lofar_map = sunpy.map.Map(data, new_header)
        lofar_map_rotate = lofar_map.rotate()
        bl = SkyCoord(-fov*u.arcsec, -fov*u.arcsec, frame=lofar_map_rotate.coordinate_frame)
        tr = SkyCoord(fov*u.arcsec, fov*u.arcsec, frame=lofar_map_rotate.coordinate_frame)
        lofar_submap = lofar_map_rotate.submap(bottom_left=bl, top_right=tr)
        return lofar_submap


    def plot_image(self,log_scale=False,fov=2500,FWHM=False,gaussian_sigma=0,
                ax_plt=None,**kwargs):
        if self.havedata:
            t_cur_datetime = self.t_obs
            solar_PA = sun_coord.P(self.t_obs).degree
            freq_cur = self.freq
            [b_maj,b_min,b_angel] = self.get_beam()
            b_maj = b_maj*3600
            b_min = b_min*3600
            data_new = gaussian_filter(self.data_xy_calib,sigma=gaussian_sigma)
            xx = self.xx
            yy = self.yy

            if ax_plt is None:
                fig=plt.figure()#num=None, figsize=(8, 6),dpi=120)
                ax = plt.gca()
            else:
                fig=plt.gcf()#num=None, figsize=(8, 6),dpi=120)
                ax = ax_plt
                
            #cmap_now = 'CMRmap_r'#,'gist_ncar_r','gist_heat'
            
            # set some default values
            if 'cmap' not in kwargs:
                kwargs['cmap'] = 'gist_heat'
            if 'vmin' not in kwargs:
                kwargs['vmin'] = 0
            if log_scale:
                data_new = 10*np.log10(data_new)
                kwargs['vmin'] = np.mean(data_new)-2*np.std(data_new)
            if 'vmax' not in kwargs:
                kwargs['vmax'] = 0.8*np.nanmax(data_new)
            ax.text(fov*0.55, fov*0.87, str(round(freq_cur,2)).ljust(5,'0') + 'MHz',color='w')
            circle1 = plt.Circle((0,0), 960, color='C0',fill=False)
            beam0 = Ellipse((-fov*0.3, -fov*0.9), b_maj, b_min, -(b_angel-solar_PA),color='w')
            
            #print(b_maj,b_min,b_angel,solar_PA)
            ax.text(-fov*0.35, -fov*0.9,'Beam shape:',horizontalalignment='right',verticalalignment='center' ,color='w')
            ax.add_artist(circle1)
            ax.add_artist(beam0)
            
            im = ax.imshow(data_new,interpolation='nearest', origin='lower',
                            extent=(min(xx),max(xx),min(yy),max(yy)),**kwargs)

            if FWHM:
                FWHM_thresh=0.5*(np.max(data_new))
                ax.contour(xx,yy,data_new,levels=[FWHM_thresh],colors=['deepskyblue'])
                
            
            plt.setp(ax,xlabel = 'X (ArcSec)',ylabel = 'Y (ArcSec)',
                    xlim=[-fov,fov],ylim=[-fov,fov],
                    title=str(t_cur_datetime))
            #plt.show()
            return [fig,ax,im]

        else:
            print("No data loaded")
            
