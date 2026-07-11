//! vtracer Python module for iOS — API-identical to PyPI vtracer 0.6.11's
//! `convert_raw_image_to_svg`, rebuilt on pyo3 0.28 (abi3) so it cross-
//! compiles for aarch64-apple-ios. Conversion core is the unmodified
//! `vtracer` crate.

use image::{io::Reader, ImageFormat};
use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use std::io::{BufReader, Cursor};
use visioncortex::{ColorImage, PathSimplifyMode};
use vtracer::{convert, ColorMode, Config, Hierarchical};

#[allow(clippy::too_many_arguments)]
fn construct_config(
    colormode: Option<&str>,
    hierarchical: Option<&str>,
    mode: Option<&str>,
    filter_speckle: Option<usize>,
    color_precision: Option<i32>,
    layer_difference: Option<i32>,
    corner_threshold: Option<i32>,
    length_threshold: Option<f64>,
    max_iterations: Option<usize>,
    splice_threshold: Option<i32>,
    path_precision: Option<u32>,
) -> Config {
    let color_mode = match colormode.unwrap_or("color") {
        "binary" => ColorMode::Binary,
        _ => ColorMode::Color,
    };
    let hierarchical = match hierarchical.unwrap_or("stacked") {
        "cutout" => Hierarchical::Cutout,
        _ => Hierarchical::Stacked,
    };
    let mode = match mode.unwrap_or("spline") {
        "polygon" => PathSimplifyMode::Polygon,
        "none" => PathSimplifyMode::None,
        _ => PathSimplifyMode::Spline,
    };
    Config {
        color_mode,
        hierarchical,
        filter_speckle: filter_speckle.unwrap_or(4),
        color_precision: color_precision.unwrap_or(6),
        layer_difference: layer_difference.unwrap_or(16),
        mode,
        corner_threshold: corner_threshold.unwrap_or(60),
        length_threshold: length_threshold.unwrap_or(4.0),
        max_iterations: max_iterations.unwrap_or(10),
        splice_threshold: splice_threshold.unwrap_or(45),
        path_precision,
    }
}

#[pyfunction]
#[pyo3(signature = (img_bytes, img_format=None, colormode=None,
    hierarchical=None, mode=None, filter_speckle=None,
    color_precision=None, layer_difference=None, corner_threshold=None,
    length_threshold=None, max_iterations=None, splice_threshold=None,
    path_precision=None))]
#[allow(clippy::too_many_arguments)]
fn convert_raw_image_to_svg(
    img_bytes: Vec<u8>,
    img_format: Option<&str>,
    colormode: Option<&str>,
    hierarchical: Option<&str>,
    mode: Option<&str>,
    filter_speckle: Option<usize>,
    color_precision: Option<i32>,
    layer_difference: Option<i32>,
    corner_threshold: Option<i32>,
    length_threshold: Option<f64>,
    max_iterations: Option<usize>,
    splice_threshold: Option<i32>,
    path_precision: Option<u32>,
) -> PyResult<String> {
    let config = construct_config(
        colormode,
        hierarchical,
        mode,
        filter_speckle,
        color_precision,
        layer_difference,
        corner_threshold,
        length_threshold,
        max_iterations,
        splice_threshold,
        path_precision,
    );
    let mut img_reader = Reader::new(BufReader::new(Cursor::new(img_bytes)));
    let fmt = img_format.and_then(ImageFormat::from_extension);
    let decoded = match fmt {
        Some(f) => {
            img_reader.set_format(f);
            img_reader.decode()
        }
        None => img_reader
            .with_guessed_format()
            .map_err(|_| PyException::new_err("Unrecognized image format. "))?
            .decode(),
    };
    let img = decoded
        .map_err(|_| PyException::new_err("Failed to decode img_bytes. "))?
        .to_rgba8();
    let (width, height) = (img.width() as usize, img.height() as usize);
    let img = ColorImage {
        pixels: img.as_raw().to_vec(),
        width,
        height,
    };
    let svg = convert(img, config)
        .map_err(|_| PyException::new_err("Failed to convert the image. "))?;
    Ok(format!("{}", svg))
}

#[pymodule]
fn vtracer(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(convert_raw_image_to_svg, m)?)?;
    Ok(())
}
