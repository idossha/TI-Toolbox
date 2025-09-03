#!/usr/bin/env python3
"""
Model Training Module for TI-Toolbox Classifier

Handles SVM training with nested cross-validation.
"""

import numpy as np
from sklearn.svm import SVC
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, roc_auc_score
from typing import Dict, Any, List
import logging


class ModelTrainer:
    """Handles SVM model training with nested cross-validation."""
    
    def __init__(self, n_jobs: int = -1, logger: logging.Logger = None):
        """
        Initialize model trainer.
        
        Args:
            n_jobs: Number of CPU cores for parallel processing
            logger: Logger instance
        """
        self.n_jobs = n_jobs
        self.logger = logger or logging.getLogger(__name__)
        self.model = None
    
    def train_voxel_wise(self, resp_data: np.ndarray, nonresp_data: np.ndarray,
                        feature_extractor, p_threshold: float = 0.01) -> Dict[str, Any]:
        """
        Train SVM using voxel-wise features with nested CV.
        
        Args:
            resp_data: Responder data
            nonresp_data: Non-responder data
            feature_extractor: FeatureExtractor instance for fold-wise feature selection
            p_threshold: P-value threshold for feature selection
            
        Returns:
            Training results dictionary
        """
        # Combine data
        X = np.vstack([resp_data, nonresp_data])
        y = np.hstack([np.ones(len(resp_data)), -np.ones(len(nonresp_data))])
        
        n_samples = X.shape[0]
        n_features = X.shape[1]
        
        self.logger.info(f"Training with {n_samples} samples and {n_features} features")
        
        # Nested cross-validation setup
        outer_cv_folds = min(6, n_samples // 3)
        inner_cv_folds = min(5, n_samples // 4)
        
        self.logger.info(f"Using {outer_cv_folds}-fold outer CV with {inner_cv_folds}-fold inner CV")
        
        # Outer CV loop
        outer_cv = StratifiedKFold(n_splits=outer_cv_folds, shuffle=True, random_state=42)
        outer_scores = []
        outer_aucs = []
        fold_results = []
        all_weights = []
        
        for fold_idx, (train_idx, test_idx) in enumerate(outer_cv.split(X, y)):
            self.logger.info(f"Processing outer fold {fold_idx + 1}/{outer_cv_folds}")
            
            # Split data
            X_train_outer, X_test_outer = X[train_idx], X[test_idx]
            y_train_outer, y_test_outer = y[train_idx], y[test_idx]
            
            # Feature selection on training data only
            resp_train_data = X_train_outer[y_train_outer == 1]
            nonresp_train_data = X_train_outer[y_train_outer == -1]
            
            fold_significant_mask = feature_extractor.perform_feature_selection_fold(
                resp_train_data, nonresp_train_data, p_threshold
            )
            
            if np.sum(fold_significant_mask) == 0:
                self.logger.warning(f"No significant features in fold {fold_idx + 1}, using top features")
                fold_significant_mask = self._get_top_features_fallback(
                    resp_train_data, nonresp_train_data, min(100, n_features)
                )
            
            # Extract significant features
            X_train_selected = X_train_outer[:, fold_significant_mask]
            X_test_selected = X_test_outer[:, fold_significant_mask]
            
            # Inner CV for hyperparameter optimization
            fold_results_dict = self._train_fold(
                X_train_selected, y_train_outer, X_test_selected, y_test_outer,
                inner_cv_folds, fold_idx + 1
            )
            
            outer_scores.append(fold_results_dict['accuracy'])
            outer_aucs.append(fold_results_dict['auc'])
            
            # Store weights mapped back to full feature space
            fold_weights = np.zeros(n_features)
            fold_weights[fold_significant_mask] = fold_results_dict['weights']
            all_weights.append(fold_weights)
            
            fold_results.append(fold_results_dict)
        
        return self._compile_results(outer_scores, outer_aucs, all_weights, fold_results, 
                                   "Nested Cross-Validation (Albizu et al. 2020)")
    
    def train_roi_based(self, resp_features: np.ndarray, nonresp_features: np.ndarray,
                       roi_ids: List[int]) -> Dict[str, Any]:
        """
        Train SVM using ROI-averaged features.
        
        Args:
            resp_features: Responder ROI features
            nonresp_features: Non-responder ROI features
            roi_ids: List of ROI IDs
            
        Returns:
            Training results dictionary
        """
        # Combine data
        X = np.vstack([resp_features, nonresp_features])
        y = np.hstack([np.ones(len(resp_features)), -np.ones(len(nonresp_features))])
        
        n_samples = X.shape[0]
        n_features = X.shape[1]
        
        self.logger.info(f"Training with {n_samples} samples and {n_features} ROI features")
        self.logger.info(f"Feature dimensionality reduced from ~300K voxels to {n_features} ROIs")
        
        # Nested cross-validation (no feature selection needed)
        outer_cv_folds = min(6, n_samples // 3)
        inner_cv_folds = min(5, n_samples // 4)
        
        self.logger.info(f"Using {outer_cv_folds}-fold outer CV with {inner_cv_folds}-fold inner CV")
        
        # Outer CV loop
        outer_cv = StratifiedKFold(n_splits=outer_cv_folds, shuffle=True, random_state=42)
        outer_scores = []
        outer_aucs = []
        fold_results = []
        all_weights = []
        
        for fold_idx, (train_idx, test_idx) in enumerate(outer_cv.split(X, y)):
            self.logger.info(f"Processing outer fold {fold_idx + 1}/{outer_cv_folds}")
            
            # Split data
            X_train_outer, X_test_outer = X[train_idx], X[test_idx]
            y_train_outer, y_test_outer = y[train_idx], y[test_idx]
            
            # Train fold (no feature selection needed)
            fold_results_dict = self._train_fold(
                X_train_outer, y_train_outer, X_test_outer, y_test_outer,
                inner_cv_folds, fold_idx + 1
            )
            
            outer_scores.append(fold_results_dict['accuracy'])
            outer_aucs.append(fold_results_dict['auc'])
            all_weights.append(fold_results_dict['weights'])
            fold_results.append(fold_results_dict)
        
        # Train final model on all data
        pipeline_final = Pipeline([
            ('scaler', StandardScaler()),
            ('svm', SVC(kernel='linear', probability=True, random_state=42, C=1.0))
        ])
        pipeline_final.fit(X, y)
        self.model = pipeline_final
        
        results = self._compile_results(outer_scores, outer_aucs, all_weights, fold_results,
                                      "ROI-based Nested Cross-Validation")
        results['roi_ids'] = roi_ids
        results['n_roi_features'] = n_features
        
        # Add ROI importance analysis
        avg_weights = np.mean(all_weights, axis=0)
        roi_importance = []
        for i, roi_id in enumerate(roi_ids):
            roi_importance.append({
                'roi_id': roi_id,
                'weight': avg_weights[i],
                'abs_weight': abs(avg_weights[i])
            })
        
        # Sort by absolute weight (importance)
        roi_importance.sort(key=lambda x: x['abs_weight'], reverse=True)
        results['roi_importance'] = roi_importance
        
        return results
    
    def _train_fold(self, X_train: np.ndarray, y_train: np.ndarray,
                   X_test: np.ndarray, y_test: np.ndarray,
                   inner_cv_folds: int, fold_num: int) -> Dict[str, Any]:
        """Train a single CV fold."""
        # Inner CV for hyperparameter optimization
        inner_cv = StratifiedKFold(n_splits=inner_cv_folds, shuffle=True, random_state=42)
        
        # Create pipeline
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('svm', SVC(kernel='linear', probability=True, random_state=42))
        ])
        
        # Parameter grid
        param_grid = {'svm__C': [0.001, 0.01, 0.1, 1, 10, 100]}
        
        # Grid search
        grid_search = GridSearchCV(
            pipeline, param_grid, cv=inner_cv,
            scoring='accuracy', n_jobs=self.n_jobs
        )
        
        # Fit and test
        grid_search.fit(X_train, y_train)
        test_predictions = grid_search.predict(X_test)
        test_probabilities = grid_search.predict_proba(X_test)[:, 1]
        
        # Calculate performance
        fold_accuracy = accuracy_score(y_test, test_predictions)
        fold_auc = roc_auc_score(y_test, test_probabilities)
        
        self.logger.info(f"  Fold {fold_num}: Accuracy={fold_accuracy:.3f}, "
                        f"AUC={fold_auc:.3f}, C={grid_search.best_params_['svm__C']}")
        
        return {
            'fold': fold_num,
            'accuracy': fold_accuracy,
            'auc': fold_auc,
            'n_features': X_train.shape[1],
            'best_C': grid_search.best_params_['svm__C'],
            'n_train': len(y_train),
            'n_test': len(y_test),
            'weights': grid_search.best_estimator_.named_steps['svm'].coef_[0]
        }
    
    def _compile_results(self, outer_scores: List[float], outer_aucs: List[float],
                        all_weights: List[np.ndarray], fold_results: List[Dict],
                        method_name: str) -> Dict[str, Any]:
        """Compile final training results."""
        mean_accuracy = np.mean(outer_scores)
        std_accuracy = np.std(outer_scores)
        mean_auc = np.mean(outer_aucs)
        
        # Calculate confidence interval
        ci_lower = mean_accuracy - 1.96 * std_accuracy
        ci_upper = mean_accuracy + 1.96 * std_accuracy
        
        # Average weights across folds
        avg_weights = np.mean(all_weights, axis=0)
        
        results = {
            'weights': avg_weights,
            'cv_accuracy': mean_accuracy * 100,
            'cv_std': std_accuracy * 100,
            'roc_auc': mean_auc,
            'confidence_interval': (ci_lower * 100, ci_upper * 100),
            'best_C': None,  # Not meaningful in nested CV
            'method': method_name,
            'fold_results': fold_results
        }
        
        self.logger.info(f"Training Results:")
        self.logger.info(f"  Accuracy: {mean_accuracy*100:.1f}% ± {std_accuracy*100:.1f}%")
        self.logger.info(f"  95% CI: [{ci_lower*100:.1f}%, {ci_upper*100:.1f}%]")
        self.logger.info(f"  ROC-AUC: {mean_auc:.3f}")
        
        return results
    
    def _get_top_features_fallback(self, resp_data: np.ndarray, nonresp_data: np.ndarray,
                                 n_features: int) -> np.ndarray:
        """Fallback method to select top features by t-statistic magnitude."""
        n_voxels = resp_data.shape[1]
        t_stats = np.zeros(n_voxels)
        
        for voxel_idx in range(n_voxels):
            resp_vals = resp_data[:, voxel_idx]
            nonresp_vals = nonresp_data[:, voxel_idx]
            
            if np.var(resp_vals) > 0 or np.var(nonresp_vals) > 0:
                try:
                    t_stat, _ = stats.ttest_ind(resp_vals, nonresp_vals, equal_var=False)
                    t_stats[voxel_idx] = abs(t_stat) if not np.isnan(t_stat) else 0
                except:
                    t_stats[voxel_idx] = 0
        
        # Select top features
        top_indices = np.argsort(t_stats)[-n_features:]
        significant_mask = np.zeros(n_voxels, dtype=bool)
        significant_mask[top_indices] = True
        
        return significant_mask
