export type InfrastructurePoint = {
  id: string;
  name: string;
  lat: number;
  lon: number;
  region: string;
};

export type TransmissionLine = {
  id: string;
  name: string;
  coordinates: [number, number][];
};

export const generationStations: InfrastructurePoint[] = [
  {
    id: "point-lisas",
    name: "Point Lisas",
    lat: 10.388,
    lon: -61.5,
    region: "Southwest Trinidad",
  },
  {
    id: "penal",
    name: "Penal",
    lat: 10.166,
    lon: -61.44,
    region: "South Trinidad",
  },
  {
    id: "cove-tobago",
    name: "Cove Tobago",
    lat: 11.179,
    lon: -60.737,
    region: "Tobago",
  },
  {
    id: "port-of-spain-gas",
    name: "Port of Spain",
    lat: 10.6668,
    lon: -61.5189,
    region: "Northwest Trinidad",
  },
];

export const substations: InfrastructurePoint[] = [
  {
    id: "pos-substation",
    name: "Port of Spain Substation",
    lat: 10.6705,
    lon: -61.514,
    region: "Northwest Trinidad",
  },
  {
    id: "san-fernando-substation",
    name: "San Fernando Substation",
    lat: 10.282,
    lon: -61.463,
    region: "South Trinidad",
  },
  {
    id: "arima-substation",
    name: "Arima Substation",
    lat: 10.636,
    lon: -61.282,
    region: "East Trinidad",
  },
  {
    id: "tobago-substation",
    name: "Tobago Substation",
    lat: 11.176,
    lon: -60.732,
    region: "Tobago",
  },
];

export const loadCenters: InfrastructurePoint[] = [
  {
    id: "load-port-of-spain",
    name: "Port of Spain",
    lat: 10.6668,
    lon: -61.5189,
    region: "Primary load center",
  },
  {
    id: "load-chaguanas",
    name: "Chaguanas",
    lat: 10.5167,
    lon: -61.4167,
    region: "Central Trinidad",
  },
  {
    id: "load-san-fernando",
    name: "San Fernando",
    lat: 10.2903,
    lon: -61.4531,
    region: "South Trinidad",
  },
  {
    id: "load-arima",
    name: "Arima",
    lat: 10.633,
    lon: -61.283,
    region: "East Trinidad",
  },
  {
    id: "load-scarborough",
    name: "Scarborough",
    lat: 11.1833,
    lon: -60.7333,
    region: "Tobago",
  },
];

export const transmissionLines: TransmissionLine[] = [
  {
    id: "south-corridor",
    name: "South Corridor",
    coordinates: [
      [10.388, -61.5],
      [10.2903, -61.4531],
      [10.5167, -61.4167],
    ],
  },
  {
    id: "north-east-backbone",
    name: "North-East Backbone",
    coordinates: [
      [10.6668, -61.5189],
      [10.5167, -61.4167],
      [10.633, -61.283],
    ],
  },
  {
    id: "tobago-link",
    name: "Tobago Link",
    coordinates: [
      [11.179, -60.737],
      [11.1833, -60.7333],
    ],
  },
];
