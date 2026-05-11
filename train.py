import lightning.pytorch as pl
from lightning.pytorch.callbacks import EarlyStopping, LearningRateMonitor
from pytorch_forecasting import TemporalFusionTransformer
from pytorch_forecasting.metrics import QuantileLoss
import torch
torch.set_float32_matmul_precision('medium')
from pytorch_forecasting import TimeSeriesDataSet, GroupNormalizer, NaNLabelEncoder
import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("historical_bpa_generation_data.csv", nrows=8640)

def prepare_tft_data(df):
    df = df.copy()
    if 'Date/Time' in df.columns:
        df['Date/Time'] = pd.to_datetime(df['Date/Time'])
        df = df.set_index('Date/Time')
    
    df = df.resample('5min').mean()
    
    df = df.interpolate(method='time')
    
    df['time_idx'] = (df.index - df.index.min()).total_seconds() // 300
    df['time_idx'] = df['time_idx'].astype(int)
    
    df['hour'] = df.index.hour.astype(str)
    df['day_of_week'] = df.index.dayofweek.astype(str)
    df['agency'] = 'BPA'
    
    df['Net_Load'] = df['Load'] - (df['Wind'] + df['Solar'])
    
    return df


if __name__ == '__main__':
        
    prepared_df = prepare_tft_data(df)

    # Configuration
    max_prediction_length = 288  # 24 hours (12 steps/hr * 24)
    max_encoder_length = 2016    # 1 week (7 days * 288)
    training_cutoff = prepared_df['time_idx'].max() - max_prediction_length

    training = TimeSeriesDataSet(
        prepared_df[lambda x: x.time_idx <= training_cutoff],
        time_idx="time_idx",
        target="Net_Load",
        group_ids=["agency"],
        min_encoder_length=max_encoder_length // 2,
        max_encoder_length=max_encoder_length,
        min_prediction_length=1,
        max_prediction_length=max_prediction_length,
        static_categoricals=["agency"],
        time_varying_known_categoricals=["hour", "day_of_week"],
        time_varying_known_reals=["time_idx"], 
        time_varying_unknown_reals=[
            "Net_Load", "Load", "Wind", "Solar", 
            "Hydro", "Nuclear", "Fossil/Biomass"
        ],
        categorical_encoders={
            "hour": NaNLabelEncoder(add_nan=True),
            "day_of_week": NaNLabelEncoder(add_nan=True)
        },
        target_normalizer=GroupNormalizer(groups=["agency"], transformation="softplus"),
        add_relative_time_idx=True,
        add_target_scales=True,
        add_encoder_length=True,
    )

    validation = TimeSeriesDataSet.from_dataset(training, prepared_df, predict=True, stop_randomization=True)

    train_dataloader = training.to_dataloader(train=True, batch_size=64, num_workers=6, persistent_workers=True)
    val_dataloader = validation.to_dataloader(train=False, batch_size=64, num_workers=6, persistent_workers=True)

    print(f"Training set: {len(training)} samples")
    print(f"Validation set: {len(validation)} samples")

    # TFT Config
    tft = TemporalFusionTransformer.from_dataset(
        training,
        learning_rate=0.03,
        hidden_size=32,        
        attention_head_size=4,
        dropout=0.1,
        hidden_continuous_size=16,
        loss=QuantileLoss(),   
        log_interval=10,
        reduce_on_plateau_patience=4,
    )

    # Trainer setup
    trainer = pl.Trainer(
        logger=pl.loggers.CSVLogger("logs"),
        max_epochs=8,
        accelerator="gpu",      
        devices=1,
        callbacks=[
            EarlyStopping(monitor="val_loss", patience=5),
            LearningRateMonitor(logging_interval="step")
        ],
    )
    
    # Model fit
    
    trainer.fit(tft, train_dataloaders = train_dataloader, val_dataloaders = val_dataloader)
    best_model_path = trainer.checkpoint_callback.best_model_path
    print(f"Best model saved at: {best_model_path}")

    metrics = pd.read_csv("logs/lightning_logs/version_9/metrics.csv")
    epoch_metrics = metrics.groupby("epoch").mean()

    plt.figure(figsize=(10, 5))
    plt.plot(epoch_metrics["train_loss_epoch"], label="Training Loss")
    plt.plot(epoch_metrics["val_loss"], label="Validation Loss")
    plt.xlabel("Epoch")
    plt.ylabel("Loss")
    plt.title("Net Load Prediction - TFT Training History")
    plt.legend()
    plt.show() 