use std::sync::{Arc, Mutex};

use cpal::{
    traits::{DeviceTrait, HostTrait, StreamTrait},
    ChannelCount, SampleFormat,
};
use dasp::{sample::ToSample, Sample};
use eframe::egui;
use std::collections::VecDeque;
use vosk::{DecodingState, Model, Recognizer};

fn main() {
    let model_path = "vosk_model";

    let audio_input_device = cpal::default_host()
        .default_input_device()
        .expect("No input device connected");

    let config = audio_input_device
        .default_input_config()
        .expect("Failed to load default input config");
    let channels = config.channels();

    let model = Model::new(model_path).expect("Could not create the model");
    let mut recognizer = Recognizer::new(&model, config.sample_rate().0 as f32)
        .expect("Could not create the Recognizer");

    let lines = Arc::new(Mutex::new(VecDeque::from([
        String::from(""),
        String::from(""),
        String::from(""),
    ])));

    recognizer.set_max_alternatives(0);
    recognizer.set_words(false);
    recognizer.set_partial_words(true);

    let recognizer = Arc::new(Mutex::new(recognizer));

    let err_fn = move |err| {
        eprintln!("an error occurred on stream: {}", err);
    };
    let lines_clone = lines.clone();

    let recognizer_clone = recognizer.clone();
    let stream = match config.sample_format() {
        SampleFormat::F32 => audio_input_device.build_input_stream(
            &config.into(),
            move |data: &[f32], _| {
                recognize(
                    &mut recognizer_clone.lock().unwrap(),
                    data,
                    channels,
                    lines.clone(),
                )
            },
            err_fn,
            None,
        ),
        SampleFormat::U16 => audio_input_device.build_input_stream(
            &config.into(),
            move |data: &[u16], _| {
                recognize(
                    &mut recognizer_clone.lock().unwrap(),
                    data,
                    channels,
                    lines.clone(),
                )
            },
            err_fn,
            None,
        ),
        SampleFormat::I16 => audio_input_device.build_input_stream(
            &config.into(),
            move |data: &[i16], _| {
                recognize(
                    &mut recognizer_clone.lock().unwrap(),
                    data,
                    channels,
                    lines.clone(),
                )
            },
            err_fn,
            None,
        ),
        _ => {
            panic!("wrong sample format")
        }
    }
    .expect("Could not build stream");

    stream.play().expect("Could not play stream");
    println!("Recording...");

    // std::thread::sleep(record_duration);
    let native_options = eframe::NativeOptions::default();

    eframe::run_native(
        "My egui App",
        native_options,
        Box::new(|cc| Ok(Box::new(MyEguiApp::new(cc, lines_clone)))),
    )
    .expect("Can't run 'egui' window");

    drop(stream);

    // println!("{:#?}", recognizer.lock().unwrap().final_result());
}

fn recognize<T: Sample + ToSample<i16>>(
    recognizer: &mut Recognizer,
    data: &[T],
    channels: ChannelCount,
    lines: Arc<Mutex<VecDeque<String>>>,
) {
    let data: Vec<i16> = data.iter().map(|v| v.to_sample()).collect();
    let data = if channels != 1 {
        stereo_to_mono(&data)
    } else {
        data
    };

    let state = recognizer.accept_waveform(&data);
    match state {
        DecodingState::Running => {
            // println!("partial: {:#?}", recognizer.partial_result());
        }
        DecodingState::Finalized => {
            // Result will always be multiple because we called set_max_alternatives
            let string = recognizer.result().single().unwrap().text.to_string();
            // println!("result: {:#?}", &string);
            if string.len() == 0 {
                return;
            }
            {
                let mut lines_vec = lines.lock().unwrap();

                lines_vec.pop_front();
                lines_vec.push_back(string);
            }
        }
        DecodingState::Failed => eprintln!("error"),
    }
}

pub fn stereo_to_mono(input_data: &[i16]) -> Vec<i16> {
    let mut result = Vec::with_capacity(input_data.len() / 2);
    result.extend(
        input_data
            .chunks_exact(2)
            .map(|chunk| chunk[0] / 2 + chunk[1] / 2),
    );

    result
}

struct MyEguiApp {
    lines: Arc<Mutex<VecDeque<String>>>,
}

impl MyEguiApp {
    fn new(cc: &eframe::CreationContext<'_>, lines: Arc<Mutex<VecDeque<String>>>) -> Self {
        cc.egui_ctx.set_pixels_per_point(3.);
        // Customize egui here with cc.egui_ctx.set_fonts and cc.egui_ctx.set_visuals.
        // Restore app state using cc.storage (requires the "persistence" feature).
        // Use the cc.gl (a glow::Context) to create graphics shaders and buffers that you can use
        // for e.g. egui::PaintCallback.
        Self { lines }
    }
}

impl eframe::App for MyEguiApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.label(self.lines.lock().unwrap().get(0).unwrap());
            ui.label(self.lines.lock().unwrap().get(1).unwrap());
            ui.label(self.lines.lock().unwrap().get(2).unwrap());
        });
        ctx.request_repaint();
    }
}
