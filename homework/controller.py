import pystk


def control(aim_point, current_vel, steer_gain=6, skid_thresh=0.25, target_vel=25, aim_point_post=None):
    import numpy as np
    #this seems to initialize an object
    action = pystk.Action()

    #compute acceleration
    if abs(aim_point[0]) > 0.15:
        action.acceleration = 0.5
    else:
        action.acceleration = 1
    
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
    
    if aim_point_post is not None:

        # Compute skidding
        if abs(aim_point_post[0]) > skid_thresh + 0.1:
            action.drift = True
            action.steer = np.clip((steer_gain*2) * aim_point_post[0], -1, 1)
        else:
            action.drift = False
            if abs(aim_point[0]) > 0.15:
                action.acceleration= 1
        

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
