import { useEffect, useRef } from "react";
import { latLng, latLngBounds, type Map as LeafletMap } from "leaflet";
import { useMap } from "react-leaflet";

import {
  getCurrentWindField,
  WIND_FIELD_EXTENT,
  type WindFieldSample,
} from "../services/windField";

const FIELD_BOUNDS = latLngBounds(
  [WIND_FIELD_EXTENT.south, WIND_FIELD_EXTENT.west],
  [WIND_FIELD_EXTENT.north, WIND_FIELD_EXTENT.east],
);
const PARTICLE_COUNT = 220;
const MAX_PARTICLE_AGE = 110;
const FLOW_SCALE = 0.0011;
const REFRESH_INTERVAL_MS = 15 * 60 * 1000;

type WindFlowStatus = "loading" | "active" | "error";

interface WindFlowLayerProps {
  onStatusChange: (status: WindFlowStatus) => void;
}

interface Particle {
  latitude: number;
  longitude: number;
  age: number;
}

interface WindVector {
  east: number;
  north: number;
  speed: number;
}

export default function WindFlowLayer({
  onStatusChange,
}: WindFlowLayerProps) {
  const map = useMap();
  const statusCallbackRef = useRef(onStatusChange);

  useEffect(() => {
    statusCallbackRef.current = onStatusChange;
  }, [onStatusChange]);

  useEffect(() => {
    const abortController = new AbortController();
    let animationFrame = 0;
    let refreshTimer = 0;
    let canvas: HTMLCanvasElement | null = null;
    let context: CanvasRenderingContext2D | null = null;
    let samples: WindFieldSample[] = [];
    let particles: Particle[] = [];
    let previousTimestamp = performance.now();
    let isMapMoving = false;

    const resizeCanvas = () => {
      if (!canvas || !context) {
        return;
      }

      const size = map.getSize();
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(size.x * pixelRatio);
      canvas.height = Math.round(size.y * pixelRatio);
      canvas.style.width = `${size.x}px`;
      canvas.style.height = `${size.y}px`;
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      context.clearRect(0, 0, size.x, size.y);
    };

    const resetParticle = (particle: Particle) => {
      const visibleBounds = map.getBounds();
      const south = Math.max(FIELD_BOUNDS.getSouth(), visibleBounds.getSouth());
      const north = Math.min(FIELD_BOUNDS.getNorth(), visibleBounds.getNorth());
      const west = Math.max(FIELD_BOUNDS.getWest(), visibleBounds.getWest());
      const east = Math.min(FIELD_BOUNDS.getEast(), visibleBounds.getEast());
      const hasVisibleIntersection = south < north && west < east;
      const spawnSouth = hasVisibleIntersection ? south : FIELD_BOUNDS.getSouth();
      const spawnNorth = hasVisibleIntersection ? north : FIELD_BOUNDS.getNorth();
      const spawnWest = hasVisibleIntersection ? west : FIELD_BOUNDS.getWest();
      const spawnEast = hasVisibleIntersection ? east : FIELD_BOUNDS.getEast();
      const latitude =
        spawnSouth + Math.random() * (spawnNorth - spawnSouth);
      const longitude =
        spawnWest + Math.random() * (spawnEast - spawnWest);
      particle.latitude = latitude;
      particle.longitude = longitude;
      particle.age = Math.floor(Math.random() * MAX_PARTICLE_AGE);
    };

    const createParticles = () => {
      particles = Array.from({ length: PARTICLE_COUNT }, () => {
        const particle = { latitude: 0, longitude: 0, age: 0 };
        resetParticle(particle);
        return particle;
      });
    };

    const interpolateWind = (
      latitude: number,
      longitude: number,
    ): WindVector | null => {
      if (samples.length === 0) {
        return null;
      }

      const nearest = samples
        .map((sample) => {
          const latitudeDistance = sample.latitude - latitude;
          const longitudeDistance = sample.longitude - longitude;
          return {
            sample,
            distanceSquared:
              latitudeDistance * latitudeDistance +
              longitudeDistance * longitudeDistance,
          };
        })
        .sort((left, right) => left.distanceSquared - right.distanceSquared)
        .slice(0, 4);

      let totalWeight = 0;
      let east = 0;
      let north = 0;
      let speed = 0;

      nearest.forEach(({ sample, distanceSquared }) => {
        const weight = 1 / Math.max(distanceSquared, 0.0001);
        const flowRadians =
          ((sample.directionDegrees + 180) * Math.PI) / 180;
        east += Math.sin(flowRadians) * sample.speedKmh * weight;
        north += Math.cos(flowRadians) * sample.speedKmh * weight;
        speed += sample.speedKmh * weight;
        totalWeight += weight;
      });

      return totalWeight > 0
        ? {
            east: east / totalWeight,
            north: north / totalWeight,
            speed: speed / totalWeight,
          }
        : null;
    };

    const animate = (timestamp: number) => {
      animationFrame = window.requestAnimationFrame(animate);
      if (!canvas || !context || samples.length === 0 || isMapMoving) {
        previousTimestamp = timestamp;
        return;
      }

      const drawingContext = context;
      const elapsedSeconds = Math.min(
        Math.max((timestamp - previousTimestamp) / 1000, 0),
        0.05,
      );
      previousTimestamp = timestamp;
      const size = map.getSize();

      drawingContext.globalCompositeOperation = "destination-out";
      drawingContext.fillStyle = "rgba(0, 0, 0, 0.11)";
      drawingContext.fillRect(0, 0, size.x, size.y);
      drawingContext.globalCompositeOperation = "source-over";
      drawingContext.lineCap = "round";

      particles.forEach((particle) => {
        if (
          particle.age >= MAX_PARTICLE_AGE ||
          !FIELD_BOUNDS.contains([particle.latitude, particle.longitude])
        ) {
          resetParticle(particle);
        }

        const wind = interpolateWind(particle.latitude, particle.longitude);
        if (!wind) {
          resetParticle(particle);
          return;
        }

        const start = map.latLngToContainerPoint(
          latLng(particle.latitude, particle.longitude),
        );
        const cosineLatitude = Math.max(
          Math.cos((particle.latitude * Math.PI) / 180),
          0.2,
        );
        particle.latitude += wind.north * FLOW_SCALE * elapsedSeconds;
        particle.longitude +=
          (wind.east * FLOW_SCALE * elapsedSeconds) / cosineLatitude;
        particle.age += 1;

        const end = map.latLngToContainerPoint(
          latLng(particle.latitude, particle.longitude),
        );
        if (
          end.x < 0 ||
          end.y < 0 ||
          end.x > size.x ||
          end.y > size.y
        ) {
          return;
        }

        drawingContext.beginPath();
        drawingContext.moveTo(start.x, start.y);
        drawingContext.lineTo(end.x, end.y);
        drawingContext.lineWidth = wind.speed >= 30 ? 2.2 : 1.6;
        drawingContext.strokeStyle =
          wind.speed >= 35
            ? "rgba(251, 146, 60, 0.9)"
            : wind.speed >= 20
              ? "rgba(103, 232, 249, 0.88)"
              : "rgba(186, 230, 253, 0.78)";
        drawingContext.stroke();
      });
    };

    const clearForMapMovement = () => {
      isMapMoving = true;
      if (canvas && context) {
        context.clearRect(0, 0, map.getSize().x, map.getSize().y);
      }
    };

    const resumeAfterMapMovement = () => {
      isMapMoving = false;
      resizeCanvas();
      createParticles();
      previousTimestamp = performance.now();
    };

    const loadWind = async () => {
      statusCallbackRef.current("loading");
      try {
        samples = await getCurrentWindField(abortController.signal);
        if (!abortController.signal.aborted) {
          createParticles();
          statusCallbackRef.current("active");
        }
      } catch (error) {
        if (!abortController.signal.aborted) {
          console.error("Wind flow data unavailable", error);
          statusCallbackRef.current("error");
        }
      }
    };

    canvas = document.createElement("canvas");
    canvas.className = "wgdss-wind-flow-layer";
    canvas.setAttribute("aria-hidden", "true");
    context = canvas.getContext("2d");
    if (!context) {
      statusCallbackRef.current("error");
      return;
    }

    map.getContainer().appendChild(canvas);
    resizeCanvas();
    map.on("movestart zoomstart", clearForMapMovement);
    map.on("moveend zoomend resize", resumeAfterMapMovement);
    void loadWind();
    refreshTimer = window.setInterval(() => {
      void loadWind();
    }, REFRESH_INTERVAL_MS);
    animationFrame = window.requestAnimationFrame(animate);

    return () => {
      abortController.abort();
      window.clearInterval(refreshTimer);
      window.cancelAnimationFrame(animationFrame);
      map.off("movestart zoomstart", clearForMapMovement);
      map.off("moveend zoomend resize", resumeAfterMapMovement);
      canvas?.remove();
    };
  }, [map]);

  return null;
}
