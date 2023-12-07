import numpy as np
import pystk

from torch.utils.data import Dataset, DataLoader
import torchvision.transforms.functional as TF
import dense_transforms

import tqdm

RESCUE_TIMEOUT = 30
TRACK_OFFSET = 15
DATASET_PATH = 'drive_data'


class SuperTuxDataset(Dataset):
    def __init__(self, dataset_path=DATASET_PATH, transform=dense_transforms.ToTensor()):
        from PIL import Image
        from glob import glob
        from os import path
        self.data = []
        for f in glob(path.join(dataset_path, '*.csv')):
            i = Image.open(f.replace('.csv', '.png'))
            i.load()
            self.data.append((i, np.loadtxt(f, dtype=np.float32, delimiter=',')))
        self.transform = transform

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        data = self.data[idx]
        data = self.transform(*data)
        return data


def load_data(dataset_path=DATASET_PATH, transform=dense_transforms.ToTensor(), num_workers=0, batch_size=128):
    dataset = SuperTuxDataset(dataset_path, transform=transform)
    return DataLoader(dataset, num_workers=num_workers, batch_size=batch_size, shuffle=True, drop_last=True)


class PyTux:
    _singleton = None

    def __init__(self, screen_width=128, screen_height=96):
        assert PyTux._singleton is None, "Cannot create more than one pytux object"
        PyTux._singleton = self
        self.config = pystk.GraphicsConfig.hd()
        self.config.screen_width = screen_width
        self.config.screen_height = screen_height
        pystk.init(self.config)
        self.k = None

    @staticmethod
    def _point_on_track(distance, track, offset=0.0):
        """
        Get a point at `distance` down the `track`. Optionally applies an offset after the track segment if found.
        Returns a 3d coordinate
        """
        node_idx = np.searchsorted(track.path_distance[..., 1],
                                   distance % track.path_distance[-1, 1]) % len(track.path_nodes)
        d = track.path_distance[node_idx]
        x = track.path_nodes[node_idx]
        t = (distance + offset - d[0]) / (d[1] - d[0])
        return x[1] * t + x[0] * (1 - t)

    @staticmethod
    def _to_image(x, proj, view):
        p = proj @ view @ np.array(list(x) + [1])
        return np.clip(np.array([p[0] / p[-1], -p[1] / p[-1]]), -1, 1)

    def rollout(self, track, controller, planner=None, max_frames=1000, verbose=False, data_callback=None, planner_post=None):
        """
        Play a level (track) for a single round.
        :param track: Name of the track
        :param controller: low-level controller, see controller.py
        :param planner: high-level planner, see planner.py
        :param max_frames: Maximum number of frames to play for
        :param verbose: Should we use matplotlib to show the agent drive?
        :param data_callback: Rollout calls data_callback(time_step, image, 2d_aim_point) every step, used to store the
                              data
        :return: Number of steps played
        """
        if self.k is not None and self.k.config.track == track:
            self.k.restart()
            self.k.step()
        else:
            if self.k is not None:
                self.k.stop()
                del self.k
            config = pystk.RaceConfig(num_kart=1, laps=1,  track=track)
            config.players[0].controller = pystk.PlayerConfig.Controller.PLAYER_CONTROL

            self.k = pystk.Race(config)
            self.k.start()
            self.k.step()

        state = pystk.WorldState()
        track = pystk.Track()

        last_rescue = 0

        if verbose:
            import matplotlib.pyplot as plt
            fig, ax = plt.subplots(1, 1)

        for t in range(max_frames):
        #for t in tqdm.tqdm(range(max_frames)): #Agregado

            state.update()
            track.update()

            kart = state.players[0].kart

            if np.isclose(kart.overall_distance / track.length, 1.0, atol=2e-3):
                if verbose:
                    print("Finished at t=%d" % t)
                break

            proj = np.array(state.players[0].camera.projection).T
            view = np.array(state.players[0].camera.view).T

            aim_point_world = self._point_on_track(kart.distance_down_track+TRACK_OFFSET, track)
            aim_point_image = self._to_image(aim_point_world, proj, view)

            bananas= []
            for item in state.items:
                if item.type == pystk.Item.Type.BANANA:
                    bananas.append(item.location)
                
            aim_point_world_post = self._point_on_track(kart.distance_down_track+TRACK_OFFSET+10, track)
            aim_point_image_post = self._to_image(aim_point_world_post, proj, view)

            if data_callback is not None:
                data_callback(t, np.array(self.k.render_data[0].image), aim_point_image, aim_point_image_post) #Aqui se debe agregar els egundo punto

            if planner:
                image = np.array(self.k.render_data[0].image)
                aim_point_image = planner(TF.to_tensor(image)[None]).squeeze(0).cpu().detach().numpy()
                if planner_post:
                    aim_point_image_post = planner_post(TF.to_tensor(image)[None]).squeeze(0).cpu().detach().numpy()

            current_vel = np.linalg.norm(kart.velocity)
            action = controller(aim_point_image, current_vel, aim_point_post= aim_point_image_post)

            if current_vel < 1.0 and t - last_rescue > RESCUE_TIMEOUT:
                last_rescue = t
                action.rescue = True

            if verbose:
                ax.clear()
                ax.imshow(self.k.render_data[0].image)
                WH2 = np.array([self.config.screen_width, self.config.screen_height]) / 2
                
                is_banana = False
                for banana in bananas:
                    ax.add_artist(plt.Circle(WH2*(1+self._to_image(banana, proj, view)), 2, ec='Yellow', fill=False, lw=1.5))
                    #print(banana[2])
                    if np.isclose(banana[0], kart.location[0], atol=5) and np.isclose(banana[1], kart.location[1], atol=5) and np.isclose(banana[2], kart.location[2], atol=5):
                        print("Banana")
                        print(banana)
                        print(kart.location)
                        print(" ")
                        is_banana = True
                        
                        angle_banana_x = banana[0] - kart.location[0]
                        angle_banana_y = banana[1] - kart.location[1]
                        angle_banana_z = banana[2] - kart.location[2]

                        print("Angulos")
                        print(angle_banana_x)
                        print(angle_banana_y)
                        print(angle_banana_z)

                    
                
                


                ax.add_artist(plt.Circle(WH2*(1+self._to_image(kart.location, proj, view)), 2, ec='b', fill=False, lw=1.5))
                ax.add_artist(plt.Circle(WH2*(1+self._to_image(aim_point_world, proj, view)), 2, ec='Red', fill=False, lw=1.5))
                ax.add_artist(plt.Circle(WH2*(1+self._to_image(aim_point_world_post, proj, view)), 2, ec='DeepSkyBlue', fill=False, lw=1.5))
                if planner:
                    ap = self._point_on_track(kart.distance_down_track + TRACK_OFFSET, track)
                    ax.add_artist(plt.Circle(WH2*(1+aim_point_image), 2, ec='DarkRed', fill=False, lw=1.5))
                    ax.add_artist(plt.Circle(WH2*(1+aim_point_image_post), 2, ec='DarkBlue', fill=False, lw=1.5))
                plt.pause(1e-3)

            self.k.step(action)
            t += 1
        return t, kart.overall_distance / track.length

    def close(self):
        """
        Call this function, once you're done with PyTux
        """
        if self.k is not None:
            self.k.stop()
            del self.k
        pystk.clean()


if __name__ == '__main__':
    from controller import control
    from argparse import ArgumentParser
    from os import makedirs


    def noisy_control(aim_pt, vel, aim_point_post=None):
        random_aim_point = np.random.randn(*aim_pt.shape)* aim_noise
        random_vel = np.random.randn() * vel_noise
        return control(aim_pt + random_aim_point, vel + random_vel, 
                        aim_point_post=aim_point_post+random_aim_point)


    parser = ArgumentParser("Collects a dataset for the high-level planner")
    parser.add_argument('track', nargs='+')
    parser.add_argument('-o', '--output', default=DATASET_PATH)
    parser.add_argument('-n', '--n_images', default=15000, type=int)
    parser.add_argument('-m', '--steps_per_track', default=30000, type=int)
    parser.add_argument('--aim_noise', default=0.1, type=float)
    parser.add_argument('--vel_noise', default=5, type=float)
    parser.add_argument('-v', '--verbose', action='store_true')
    args = parser.parse_args()
    try:
        makedirs(args.output)
        makedirs("drive_data_2") #Agregado
    except OSError:
        pass
    pytux = PyTux()
    for track in args.track:
        n, images_per_track = 0, args.n_images // len(args.track)
        aim_noise, vel_noise = 0, 0

        print("\n\n"+track) #Agregado
        def collect(_, im, pt, pt2): #Aqui se debe agregar como parámetro el segundo punto
            from PIL import Image
            from os import path
            global n
            id = n if n < images_per_track else np.random.randint(0, n + 1)
            if id < images_per_track:
                fn = path.join(args.output, track + '_%05d' % id)
                Image.fromarray(im).save(fn + '.png')
                with open(fn + '.csv', 'w') as f:
                    f.write('%0.1f,%0.1f' % tuple(pt))

                
                #Aqui se debe agregar que escriba la posición del segundo círculo en el csv
                fn = path.join("drive_data_2", track + '_%05d' % id)
                Image.fromarray(im).save(fn + '.png')
                with open(fn + '.csv', 'w') as f:
                    f.write('%0.1f,%0.1f' % tuple(pt2))
            n += 1
        pbar = tqdm.tqdm(total=images_per_track)
        while n < images_per_track:
            steps, how_far = pytux.rollout(track, noisy_control, max_frames=1000, verbose=args.verbose, data_callback=collect)
            #print(steps, how_far) #Quitar
            # Add noise after the first round
            aim_noise, vel_noise = args.aim_noise, args.vel_noise
            
            #print(n, args.steps_per_track, images_per_track) #Agregado
            pbar.update(n)
    pytux.close()
