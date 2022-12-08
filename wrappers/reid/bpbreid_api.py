import sys
import numpy as np
import torch

from omegaconf import OmegaConf
from yacs.config import CfgNode as CN

from .bpbreid_dataset import ReidDataset
from pbtrack.core.reidentifier import ReIdentifier
from pbtrack.utils.coordinates import kp_img_to_kp_bbox, rescale_keypoints
from plugins.reid.bpbreid.scripts.main import build_config, build_torchreid_model_engine
from plugins.reid.bpbreid.tools.feature_extractor import FeatureExtractor
from plugins.reid.bpbreid.torchreid.data.data_augmentation.coco_keypoints_transforms import CocoToSixBodyMasks
from plugins.reid.bpbreid.torchreid.utils.imagetools import build_gaussian_heatmaps


from hydra.utils import to_absolute_path
sys.path.append(to_absolute_path("plugins/reid/bpbreid"))  # FIXME ugly
sys.path.append(to_absolute_path("plugins/reid"))  # FIXME ugly
import torchreid
from torchreid.data.datasets import configure_dataset_class

# need that line to not break import of torchreid ('from torchreid... import ...') inside the bpbreid.torchreid module
# to remove the 'from torchreid... import ...' error 'Unresolved reference 'torchreid' in PyCharm, right click
# on 'bpbreid' folder, then choose 'Mark Directory as' -> 'Sources root'
from bpbreid.scripts.default_config import engine_run_kwargs


class BPBReId(ReIdentifier):
    """
    TODO:
        why bbox move after strongsort?
        training
        batch process
        save config + commit hash with model weights
        model download from URL: HRNet etc
        save folder: uniform with reconnaissance
        wandb support
    """

    def __init__(self, cfg, tracking_dataset, dataset, device, save_path, model_pose, job_id):
        tracking_dataset.name = dataset.name
        tracking_dataset.nickname = dataset.nickname
        additional_args = {
            'tracking_dataset': tracking_dataset,
            'reid_config': dataset,
            'pose_model': model_pose,
        }
        torchreid.data.register_image_dataset(
            tracking_dataset.name,
            configure_dataset_class(ReidDataset, **additional_args),
            tracking_dataset.nickname,
        )
        self.device = device
        self.cfg = CN(OmegaConf.to_container(cfg, resolve=True))
        # set parts information (number of parts K and each part name),
        # depending on the original loaded masks size or the transformation applied:
        self.cfg = build_config(config_file=self.cfg)
        self.cfg.data.save_dir = save_path
        self.cfg.project.job_id = job_id
        self.cfg.use_gpu = torch.cuda.is_available()
        # Register the PoseTrack21ReID dataset to Torchreid that will be instantiated when building Torchreid engine.
        self.training_enabled = not self.cfg.test.evaluate
        self.feature_extractor = None
        self.model = None
        self.transform = CocoToSixBodyMasks()

    def preprocess(self, image):  # Tensor RGB (1, 3, H, W)
        assert 1 == image.shape[0], "Test batch size should be 1"
        input = image[0].cpu().numpy()  # -> (3, H, W)
        input = np.transpose(input, (1, 2, 0))  # -> (H, W, 3)
        input = input * 255.0
        input = input.astype(np.uint8)  # -> to uint8
        return input

    def process(self, detections, data):
        if self.feature_extractor is None:
            self.feature_extractor = FeatureExtractor(
                self.cfg,
                model_path=self.cfg.model.load_weights,
                device=self.device,
                image_size=(self.cfg.data.height, self.cfg.data.width),
                model=self.model,
                verbose=False,  # FIXME @Vladimir
            )
        mask_w, mask_h = 32, 64
        im_crops = []
        image = self.pre_process(data["image"].unsqueeze(0))  # FIXME
        all_masks = []
        for i, detection in enumerate(detections):
            bbox = detection.bbox
            pose = detection.keypoints
            l = int(bbox.x)
            t = int(bbox.y)
            r = int(bbox.x + bbox.w)
            b = int(bbox.y + bbox.h)
            crop = image[t:b, l:r]
            im_crops.append(crop)
            keypoints = np.array([[kp.x, kp.y, kp.conf] for kp in detection.keypoints])
            bbox_ltwh = np.array([l, t, r - l, b - t])
            kp_xyc_bbox = kp_img_to_kp_bbox(keypoints, bbox_ltwh)
            kp_xyc_mask = rescale_keypoints(
                kp_xyc_bbox, (bbox_ltwh[2], bbox_ltwh[3]), (mask_w, mask_h)
            )
            pixels_parts_probabilities = build_gaussian_heatmaps(
                kp_xyc_mask, mask_w, mask_h
            )
            all_masks.append(pixels_parts_probabilities)

        if im_crops:
            external_parts_masks = np.stack(all_masks, axis=0)
            embeddings, visibility_scores, body_masks, _ = self.feature_extractor(
                im_crops, external_parts_masks=external_parts_masks
            )
            for i, detection in enumerate(detections):
                detection.reid_features = embeddings[i]
                detection.visibility_score = visibility_scores[i]
                detection.body_mask = body_masks[i]
        return detections

    def train(self):
        self.engine, self.model = build_torchreid_model_engine(self.cfg)
        self.engine.run(**engine_run_kwargs(self.cfg))

    def _xywh_to_xyxy(self, bbox_xywh, width, height):
        x, y, w, h = bbox_xywh
        x1 = max(int(x - w / 2), 0)
        x2 = min(int(x + w / 2), width - 1)
        y1 = max(int(y - h / 2), 0)
        y2 = min(int(y + h / 2), height - 1)
        return x1, y1, x2, y2

# will be used to update higher
class BPBReIdentifier2(ReIdentifier):
    def __init__(self, cfg, device, tracking_dataset, dataset, save_path, model_pose, job_id):
        additional_args = {
            'tracking_dataset': tracking_dataset,
            'reid_config': dataset,
            'pose_model': model_pose,
        }
        torchreid.data.register_image_dataset(
            tracking_dataset.name,
            configure_dataset_class(ReidDataset, **additional_args),
            tracking_dataset.nickname,
        )
        self.device = device
        self.cfg = CN(OmegaConf.to_container(cfg, resolve=True))
        # set parts information (number of parts K and each part name),
        # depending on the original loaded masks size or the transformation applied:
        self.cfg = build_config(config_file=self.cfg)
        self.cfg.data.save_dir = save_path
        self.cfg.project.job_id = job_id
        self.cfg.use_gpu = torch.cuda.is_available()
        # Register the PoseTrack21ReID dataset to Torchreid that will be instantiated when building Torchreid engine.
        self.training_enabled = not self.cfg.test.evaluate
        self.feature_extractor = None
        self.model = None
        self.transform = CocoToSixBodyMasks()
        
        self.device = device
        self.cfg = CN(OmegaConf.to_container(cfg, resolve=True))
        self.cfg = build_config(config_file=self.cfg)
        '''
        datamanager = build_datamanager(cfg)
        self.model = torchreid.models.build_model(
            name=cfg.model.name,
            num_classes=datamanager.num_train_pids,
            loss=cfg.loss.name,
            pretrained=cfg.model.pretrained,
            use_gpu=cfg.use_gpu,
            config=cfg
        )
        '''
    
    def pre_process(self, detection, image):
        mask_w, mask_h = 32, 64
        l, t, r, b = detection.bbox_ltrb.astype(int)
        bbox_ltwh = np.array([l, t, r - l, b - t])
        crop = image[t:b, l:r]
        kp_xyc_bbox = kp_img_to_kp_bbox(detection.keypoints, bbox_ltwh)
        kp_xyc_mask = rescale_keypoints(
            kp_xyc_bbox, (bbox_ltwh[2], bbox_ltwh[3]), (mask_w, mask_h)
        )
        pixels_parts_probabilities = build_gaussian_heatmaps(
            kp_xyc_mask, mask_w, mask_h
        )
        return {
            "crop": crop,
            "pixels_parts_probabilities": pixels_parts_probabilities,
            "detection": detection,
        }
        
    def process(self, pre_processed_batch):
        if self.feature_extractor is None:
            self.feature_extractor = FeatureExtractor(
                self.cfg,
                model_path=self.cfg.model.load_weights,
                device=self.device,
                image_size=(self.cfg.data.height, self.cfg.data.width),
                model=self.model,
                verbose=False,  # FIXME @Vladimir
            )
        crop = pre_processed_batch["crop"]
        pixels_parts_probabilities = pre_processed_batch["pixels_parts_probabilities"]
        detection = pre_processed_batch["detection"]
        external_parts_masks = np.expand_dims(pixels_parts_probabilities, axis=0)
        embeddings, visibility_scores, body_masks, _ = self.feature_extractor(
                [crop], external_parts_masks=external_parts_masks
            )
        detection.reid_features = embeddings[0]
        detection.visibility_score = visibility_scores[0]
        detection.body_mask = body_masks[0]
        return detection

    def train(self):
        self.engine, self.model = build_torchreid_model_engine(self.cfg)
        self.engine.run(**engine_run_kwargs(self.cfg))