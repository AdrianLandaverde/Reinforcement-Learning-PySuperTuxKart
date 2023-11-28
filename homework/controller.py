import pystk


def control(aim_point, current_vel, steer_gain=6, skid_thresh=0.25, target_vel=25):
    import numpy as np
    #this seems to initialize an object
    action = pystk.Action()

    #compute acceleration
    if abs(aim_point[0]) > 0.15:
        action.acceleration = 0.3
    else:
        action.acceleration = 0.9
    
    if current_vel > target_vel:
        action.brake = True
        action.nitro = False
    else:
        action.brake = False	
        action.nitro = True
    
    # Compute steering
    action.steer = np.clip(steer_gain * aim_point[0], -1, 1)

    # Compute skidding
    if abs(aim_point[0]) > skid_thresh:
        action.drift = True
    else:
        action.drift = False

    action.fire= True

    return action




if __name__ == '__main__':
    from utils import PyTux
    from argparse import ArgumentParser

    def test_controller(args):
        import numpy as np
        pytux = PyTux()
        for t in args.track:
            steps, how_far = pytux.rollout(t, control, max_frames=1000, verbose=args.verbose)
            print(steps, how_far)
        pytux.close()


    parser = ArgumentParser()
    parser.add_argument('track', nargs='+')
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    test_controller(args)
