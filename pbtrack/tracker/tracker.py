from pbtrack.datasets.tracking_dataset import TrackingSet


class Tracker:
    def __init__(self, tracking_set: TrackingSet):
        self.gt = tracking_set
        self.predictions = None

    # TODO : use panda API for the following utils
    # Utils for loading/saving tracking results
    def save_mot(self, path):
        videos = self.video_name.unique()
        for video in videos:
            output = ''
            sub_df = self[(self['video_name'] == video) & (self['source'] == 2)].sort_values(by=['frame'])
            for index, detection in sub_df.iterrows():
                output += f"{detection['frame']}, {detection['person_id']}, {detection['bb_x']}, " + \
                          f"{detection['bb_y']}, {detection['bb_w']}, " + \
                          f"{detection['bb_h']}, {detection['bb_conf']}, -1, -1, -1\n"
            file_name = os.path.join(path, video + '.txt')
            with open(file_name, 'w+') as f:
                f.write(output)

    # FIXME maybe merge with save_pose_tracking ?
    def save_pose_estimation(self, path):
        videos = self.video_name.unique()
        for video in videos:
            video_df = self[(self['video_name'] == video)].sort_values(by=['frame'])
            detection_df = video_df[video_df['source'] >= 1]

            keypoints = detection_df.pose_xy(with_conf=True)
            annotations = []
            for ((index, detection), xys) in zip(detection_df.iterrows(), keypoints):
                annotations.append({
                    'bbox': [detection['bb_x'], detection['bb_y'],
                             detection['bb_w'], detection['bb_h']],
                    'image_id': detection['image_id'],
                    'keypoints': xys,  # FIXME score -> visibility
                    'scores': xys[:, 2],
                    'person_id': index,  # This is a dummy variable
                    'track_id': index,  # This is a dummy variable
                })

            file_paths = video_df['file_path'].unique()
            image_ids = video_df['image_id'].unique()
            images = []
            for file_path, image_id in zip(file_paths, image_ids):
                images.append({
                    'file_name': file_path,
                    'id': image_id,
                    'image_id': image_id,
                })

            file_name = os.path.join(path, video + '.json')
            with open(file_name, 'w+') as f:
                output = {
                    'images': images,
                    'annotations': annotations,
                }
                json.dump(output, f, cls=CustomEncoder)

    def save_pose_tracking(self, path):
        videos = self.video_name.unique()
        for video in videos:
            video_df = self[(self['video_name'] == video)].sort_values(by=['frame'])
            detection_df = video_df[video_df['source'] == 2]

            keypoints = detection_df.pose_xy(with_conf=True)
            annotations = []
            for ((_, detection), xys) in zip(detection_df.iterrows(), keypoints):
                annotations.append({
                    'bbox': [detection['bb_x'], detection['bb_y'],
                             detection['bb_w'], detection['bb_h']],
                    'image_id': detection['image_id'],
                    'keypoints': xys,  # FIXME score -> visibility
                    'scores': xys[:, 2],
                    'person_id': detection['person_id'],
                    'track_id': detection['person_id'],
                })

            file_paths = video_df['file_path'].unique()
            image_ids = video_df['image_id'].unique()
            images = []
            for file_path, image_id in zip(file_paths, image_ids):
                images.append({
                    'file_name': file_path,
                    'id': image_id,
                    'image_id': image_id,
                })

            file_name = os.path.join(path, video + '.json')
            with open(file_name, 'w+') as f:
                output = {
                    'images': images,
                    'annotations': annotations,
                }
                json.dump(output, f, cls=CustomEncoder)