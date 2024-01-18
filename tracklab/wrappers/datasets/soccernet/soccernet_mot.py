import os
import pandas as pd
from pathlib import Path
from tracklab.datastruct import TrackingDataset, TrackingSet


class SoccerNetMOT(TrackingDataset):
    def __init__(self, dataset_path: str, *args, **kwargs):
        self.dataset_path = Path(dataset_path)
        assert self.dataset_path.exists(), f"'{self.dataset_path}' directory does not exist. Please check the path or download the dataset following the instructions here: https://github.com/SoccerNet/sn-tracking"

        train_set = load_set(self.dataset_path / "train")
        val_set = load_set(self.dataset_path / "test")
        # test_set = load_set(self.dataset_path / "challenge")
        test_set = None

        super().__init__(dataset_path, train_set, val_set, test_set, *args, **kwargs)


def read_ini_file(file_path):
    with open(file_path, 'r') as file:
        lines = file.readlines()
    return dict(line.strip().split('=') for line in lines[1:])


def read_motchallenge_formatted_file(file_path):
    columns = ['image_id', 'track_id', 'left', 'top', 'width', 'height', 'bbox_conf', 'class', 'visibility', 'unused']
    df = pd.read_csv(file_path, header=None, names=columns)
    df['bbox_ltwh'] = df.apply(lambda row: [row['left'], row['top'], row['width'], row['height']], axis=1)
    df['person_id'] = df['track_id']  # Create person_id column with the same content as track_id
    return df[['image_id', 'track_id', 'person_id', 'bbox_ltwh', 'bbox_conf', 'class', 'visibility']]


def load_set(dataset_path):
    video_metadatas_list = []
    image_metadata_list = []
    detections_list = []
    categories_list = []

    image_counter = 0
    for video_folder in sorted(os.listdir(dataset_path)):  # Sort videos by name
        video_folder_path = os.path.join(dataset_path, video_folder)
        if os.path.isdir(video_folder_path):
            # Read gameinfo.ini
            gameinfo_path = os.path.join(video_folder_path, 'gameinfo.ini')
            gameinfo_data = read_ini_file(gameinfo_path)

            # Read seqinfo.ini
            seqinfo_path = os.path.join(video_folder_path, 'seqinfo.ini')
            seqinfo_data = read_ini_file(seqinfo_path)

            # Read ground truth detections
            gt_path = os.path.join(video_folder_path, 'gt', 'gt.txt')
            detections_df = read_motchallenge_formatted_file(gt_path)
            detections_df['image_id'] = detections_df['image_id'] - 1 + image_counter
            detections_df['video_id'] = len(video_metadatas_list) + 1
            detections_df['visibility'] = 1
            detections_list.append(detections_df)

            # Append video metadata
            nframes = int(seqinfo_data.get('seqLength', 0))
            video_metadata = {
                'id': len(video_metadatas_list) + 1,
                'name': gameinfo_data.get('name', ''),
                'nframes': nframes,
                'frame_rate': int(seqinfo_data.get('frameRate', 0)),
                'seq_length': nframes,
                'im_width': int(seqinfo_data.get('imWidth', 0)),
                'im_height': int(seqinfo_data.get('imHeight', 0)),
                'game_id': int(gameinfo_data.get('gameID', 0)),
                'action_position': int(gameinfo_data.get('actionPosition', 0)),
                'action_class': gameinfo_data.get('actionClass', ''),
                'visibility': gameinfo_data.get('visibility', ''),
                'clip_start': int(gameinfo_data.get('clipStart', 0)),
                'game_time_start': gameinfo_data.get('gameTimeStart', '').split(' - ')[1],
                # Remove the half period index
                'game_time_stop': gameinfo_data.get('gameTimeStop', '').split(' - ')[1],  # Remove the half period index
                'clip_stop': int(gameinfo_data.get('clipStop', 0)),
                'num_tracklets': int(gameinfo_data.get('num_tracklets', 0)),
                'half_period_start': int(gameinfo_data.get('gameTimeStart', '').split(' - ')[0]),
                # Add the half period start column
                'half_period_stop': int(gameinfo_data.get('gameTimeStop', '').split(' - ')[0]),
                # Add the half period stop column
            }

            # Extract categories from trackletID entries
            tracklet_attributes = {}
            for i in range(1, int(gameinfo_data.get('num_tracklets', 0)) + 1):
                tracklet_entry = gameinfo_data.get(f'trackletID_{i}', '')
                role, additional_info = tracklet_entry.split(';')
                role = role.strip().replace(' ', '_')
                additional_info = additional_info.replace(' ', '_')
                if "goalkeeper" in role:
                    if "left" in role:
                        team = "left"
                    elif "right" in role:
                        team = "right"
                    else:
                        raise ValueError(f"Unknown team for role {role}")
                    role = "goalkeeper"
                    jersey_number = int(additional_info) if additional_info.isdigit() else None
                    position = None
                    category = f"{role}_{team}_{jersey_number}" if jersey_number is not None else f"{role}_{team}"
                elif "player" in role:
                    if "left" in role:
                        team = "left"
                    elif "right" in role:
                        team = "right"
                    else:
                        raise ValueError(f"Unknown team for role {role}")
                    role = "player"
                    jersey_number = int(additional_info) if additional_info.isdigit() else None
                    position = None
                    category = f"{role}_{team}_{jersey_number}" if jersey_number is not None else f"{role}_{team}"
                elif "referee" in role:
                    team = None
                    role = "referee"
                    jersey_number = None
                    position = additional_info
                    category = f"{role}_{additional_info}"
                elif "ball" in role:
                    team = None
                    role = "ball"
                    jersey_number = None
                    position = None
                    category = f"{role}_{additional_info}"
                else:
                    assert "other" in role
                    team = None
                    role = "other"
                    jersey_number = None
                    position = None
                    category = f"{role}_{additional_info}"

                tracklet_attributes[i] = {
                    "team": team,
                    "role": role,
                    "jersey_number": jersey_number,
                    "category": category,
                    "position": position,
                }

                categories_list.append(category)

            # Assign the attributes to the detections
            for t_id, t_attributes in tracklet_attributes.items():
                for attribute in t_attributes.keys():
                    detections_df.loc[detections_df['track_id'] == t_id, attribute] = t_attributes[attribute]

            # Append video metadata
            video_metadatas_list.append(video_metadata)

            # Append image metadata
            img_folder_path = os.path.join(video_folder_path, 'img1')
            img_metadata_df = pd.DataFrame({
                'frame': [i for i in range(0, nframes)],
                'id': [image_counter + i for i in range(0, nframes)],
                'video_id': len(video_metadatas_list),
                'file_path': [os.path.join(img_folder_path, f'{i:06d}.jpg') for i in
                              range(1, nframes + 1)],

            })
            image_counter += nframes
            image_metadata_list.append(img_metadata_df)

    categories_list = [{'id': i + 1, 'name': category, 'supercategory': 'person'} for i, category in
                       enumerate(sorted(set(categories_list)))]

    # Assign the categories to the video metadata  # TODO at dataset level?
    for video_metadata in video_metadatas_list:
        video_metadata['categories'] = categories_list

    # Concatenate dataframes
    video_metadata = pd.DataFrame(video_metadatas_list)
    image_metadata = pd.concat(image_metadata_list, ignore_index=True)
    detections = pd.concat(detections_list, ignore_index=True)

    # Add category id to detections
    category_to_id = {category['name']: category['id'] for category in categories_list}
    detections['category_id'] = detections['category'].apply(lambda x: category_to_id[x])

    # Set 'id' column as the index in the detections and image dataframe
    detections['id'] = detections.index

    detections.set_index("id", drop=True, inplace=True)
    image_metadata.set_index("id", drop=True, inplace=True)
    video_metadata.set_index("id", drop=True, inplace=True)

    # Add is_labeled column to image_metadata
    image_metadata['is_labeled'] = True

    # Reorder columns in dataframes
    video_metadata_columns = ['name', 'nframes', 'frame_rate', 'seq_length', 'im_width', 'im_height', 'game_id', 'action_position',
                   'action_class', 'visibility', 'clip_start', 'game_time_start', 'clip_stop', 'game_time_stop',
                   'num_tracklets',
                   'half_period_start', 'half_period_stop', 'categories']
    video_metadata_columns.extend(set(video_metadata.columns) - set(video_metadata_columns))
    video_metadata = video_metadata[video_metadata_columns]
    image_metadata_columns = ['video_id', 'frame', 'file_path', 'is_labeled']
    image_metadata_columns.extend(set(image_metadata.columns) - set(image_metadata_columns))
    image_metadata = image_metadata[image_metadata_columns]
    detections_column_ordered = ['image_id', 'video_id', 'track_id', 'person_id', 'bbox_ltwh', 'bbox_conf', 'class', 'visibility']
    detections_column_ordered.extend(set(detections.columns) - set(detections_column_ordered))
    detections = detections[detections_column_ordered]

    return TrackingSet(
        video_metadata,
        image_metadata,
        detections,
    )