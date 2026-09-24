"""Run synthetic trajectories only; these are not athlete validation results."""
from hpt_tracking.pixel_effort import pixel_effort

if __name__ == '__main__':
    for name, speed, duration in [('Stationary',0,10), ('100 px/s for 10s',100,10),
                                  ('200 px/s for 10s',200,10), ('100 px/s for 20s',100,20)]:
        samples=[(i,speed*i/10,0) for i in range(duration*10+1)]
        r=pixel_effort(samples,10)
        print(f"{name}: {r['value']} AU (synthetic demonstration)")
