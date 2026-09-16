from datetime import date
from hashlib import sha256
from io import BytesIO
import threading
import numpy as np
from netCDF4 import Dataset, num2date
import matplotlib
matplotlib.use('Agg')
from matplotlib.figure import Figure
from backend.config import settings

RENDER_VERSION = 'fixed2025-v1'
PRODUCTS = ('temperature','humidity','pressure_wind','circulation_500')
PRODUCT_TITLES = {'temperature':'2 m temperature (C)','humidity':'2 m relative humidity (%)',
                  'pressure_wind':'Sea-level pressure (hPa) / 10 m wind','circulation_500':'500 hPa height (m) / wind'}


class WeatherStore:
    def __init__(self, path=None):
        self.path = path or settings.weather_file
        self.lock = threading.RLock()
        # netCDF4's Windows filename handling is not Unicode-safe; in-memory access preserves the source.
        file_bytes = self.path.read_bytes()
        self.source_hash = sha256(file_bytes).hexdigest()
        self.dataset = Dataset('weather',memory=file_bytes)
        if getattr(self.dataset,'aggregation_method','') != 'synthetic_daily_mean':
            raise ValueError('本联调适配器仅接受已确认的合成日均场')
        expected_units = {'T2M':'K','D2M':'K','MSL':'Pa','Z500':'m2 s-2',
                          'U10M':'m s-1','V10M':'m s-1','U500':'m s-1','V500':'m s-1'}
        for variable,unit in expected_units.items():
            if variable not in self.dataset.variables or self.dataset[variable].units != unit:
                raise ValueError(f'气象变量或单位不符合固定数据约定：{variable}')
        time = self.dataset['time']
        self.date_indices = {date(value.year,value.month,value.day):index for index,value in enumerate(num2date(time[:],time.units))}
        self.valid_dates = set()
        for day,index in self.date_indices.items():
            if all(np.isfinite(np.ma.filled(self.dataset[name][index],np.nan)).mean() >= .8 for name in expected_units):
                self.valid_dates.add(day)

    def render(self, dates):
        with self.lock:
            if any(day not in self.valid_dates for day in dates):
                raise ValueError('缺少四类图必需空间场')
            results = {}
            columns = len(dates) if len(dates) <= 4 else 4
            rows = 1 if len(dates) <= 4 else 2
            for product in PRODUCTS:
                figure = Figure(figsize=(4.1*columns,3.8*rows),layout='constrained',facecolor='#f7faf9')
                axes = figure.subplots(rows,columns,squeeze=False)
                mappable = None
                for offset,axis in enumerate(axes.flat):
                    if offset >= len(dates):
                        axis.set_visible(False)
                        continue
                    index = self.date_indices[dates[offset]]
                    is_upper = product == 'circulation_500'
                    prefix = 'upper' if is_upper else 'surface'
                    longitude = np.asarray(self.dataset[f'{prefix}_longitude'][:])
                    latitude = np.asarray(self.dataset[f'{prefix}_latitude'][:])
                    def field(name):
                        return np.ma.filled(self.dataset[name][index],np.nan)
                    if product == 'temperature':
                        mappable = axis.pcolormesh(longitude,latitude,field('T2M')-273.15,cmap='coolwarm',vmin=-10,vmax=40,shading='auto')
                    elif product == 'humidity':
                        temperature,dewpoint = field('T2M')-273.15,field('D2M')-273.15
                        humidity = np.clip(100*np.exp(17.625*dewpoint/(243.04+dewpoint)-17.625*temperature/(243.04+temperature)),0,100)
                        mappable = axis.pcolormesh(longitude,latitude,humidity,cmap='YlGnBu',vmin=0,vmax=100,shading='auto')
                    else:
                        values = field('Z500')/9.80665 if is_upper else field('MSL')/100
                        levels = np.arange(4800,6301,40) if is_upper else np.arange(940,1081,4)
                        mappable = axis.pcolormesh(longitude,latitude,values,cmap='cividis',
                                                  vmin=5000 if is_upper else 980,vmax=6100 if is_upper else 1040,shading='auto')
                        contours = axis.contour(longitude,latitude,values,levels=levels,colors='#253842',linewidths=.55)
                        axis.clabel(contours,fontsize=6,inline=True)
                        stride = 20 if is_upper else 9
                        eastward,northward = field('U500' if is_upper else 'U10M'),field('V500' if is_upper else 'V10M')
                        arrows = axis.quiver(longitude[::stride],latitude[::stride],eastward[::stride,::stride],northward[::stride,::stride],
                                            scale=500 if is_upper else 140,width=.003,color='#172e39')
                        axis.quiverkey(arrows,.84,1.06,20 if is_upper else 5,'20 m/s' if is_upper else '5 m/s',labelpos='E',fontproperties={'size':6})
                    axis.plot(121.47,31.23,marker='*',color='#b72032',markersize=8,markeredgecolor='white',markeredgewidth=.5)
                    axis.annotate('Shanghai',(121.47,31.23),xytext=(4,4),textcoords='offset points',fontsize=6)
                    axis.set(xlim=(105,135) if is_upper else (115,126),ylim=(20,45) if is_upper else (26,36),
                             title=f'D{offset+1} | {dates[offset]}',xlabel='Longitude (E)',ylabel='Latitude (N)')
                    axis.set_aspect(1/np.cos(np.deg2rad(31)))
                    axis.tick_params(labelsize=7)
                    axis.grid(alpha=.2,linewidth=.4)
                figure.suptitle(PRODUCT_TITLES[product]+' | SYNTHETIC DAILY MEAN',fontsize=11)
                figure.colorbar(mappable,ax=[axis for axis in axes.flat if axis.get_visible()],shrink=.7,pad=.02)
                output = BytesIO()
                figure.savefig(output,format='png',dpi=110)
                results[product] = output.getvalue()
                figure.clear()
            return results
