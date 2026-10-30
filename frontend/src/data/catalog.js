// Reference data for the audit form.
// Emission factors are indicative values (tCO2e per unit) based on DEFRA 2025
// and the CEA India grid factor. Replace with the official tables / backend data.

export const SOURCES = {
  grid_electricity: { name: 'Grid electricity', scope: 2, units: { kWh: 0.000716, MWh: 0.716 } },
  diesel: { name: 'Diesel', scope: 1, units: { Litres: 0.00266, kL: 2.66 } },
  petrol: { name: 'Petrol', scope: 1, units: { Litres: 0.00231 } },
  natural_gas: { name: 'Natural gas', scope: 1, units: { 'm³': 0.00202, kWh: 0.000183 } },
  coal: { name: 'Coal (industrial)', scope: 1, units: { Tonnes: 2.4, kg: 0.0024 } },
  coking_coal: { name: 'Coking coal', scope: 1, units: { Tonnes: 3.17, kg: 0.00317 } },
  furnace_oil: { name: 'Furnace oil', scope: 1, units: { Litres: 0.00318, Tonnes: 3.23 } },
  lpg: { name: 'LPG', scope: 1, units: { kg: 0.00294, Litres: 0.00156 } },
  jet_fuel: { name: 'Aviation fuel (ATF)', scope: 1, units: { Litres: 0.00254, Tonnes: 3.15 } },
  marine_fuel: { name: 'Marine fuel oil', scope: 1, units: { Tonnes: 3.11 } },
  truck_distance: { name: 'Diesel truck (distance)', scope: 1, units: { km: 0.00086 } },
  van_distance: { name: 'Petrol van (distance)', scope: 1, units: { km: 0.00025 } },
  refrigerant_r404a: { name: 'Refrigerant leak (R-404A)', scope: 1, units: { kg: 3.922 } },
  refrigerant_r134a: { name: 'Refrigerant leak (R-134a)', scope: 1, units: { kg: 1.43 } },
  urea: { name: 'Urea fertiliser', scope: 1, units: { Tonnes: 0.733 } },
  air_travel: { name: 'Business air travel', scope: 3, units: { 'passenger-km': 0.00015 } },
}

export const ALL_SOURCE_IDS = Object.keys(SOURCES)

// Reporting framework the report is prepared under.
export const FRAMEWORKS = ['GHG Protocol', 'ISO 14064-1']

// Emission factor database for Scope 1 & 3.
export const FACTOR_SOURCES = ['DEFRA 2026']

// Scope 2 grid factor (tCO2e per MWh) picked from the facility's country.
export const COUNTRIES = {
  India: { gridFactor: 0.716, gridSource: 'CEA India grid' },
  'United Kingdom': { gridFactor: 0.177, gridSource: 'DEFRA UK grid' },
  'United States': { gridFactor: 0.371, gridSource: 'EPA eGRID' },
  Singapore: { gridFactor: 0.412, gridSource: 'EMA Singapore grid' },
  'United Arab Emirates': { gridFactor: 0.404, gridSource: 'IEA UAE grid' },
}

export const FACILITY_TYPES = ['Company / plant', 'Office', 'Educational institute', 'Warehouse', 'Service setup', 'Other']

export const PERIOD_TYPES = ['Monthly', 'Quarterly', 'Annual', 'Custom']

// industry -> sub-sectors -> process steps -> allowed energy sources
export const INDUSTRIES = [
  {
    id: 'steel',
    name: 'Steel & Heavy Manufacturing',
    icon: 'factory',
    subsectors: [
      {
        id: 'integrated',
        name: 'Integrated Steel Plant',
        processes: [
          { name: 'Coke Oven Combustion', sources: ['coking_coal', 'coal', 'natural_gas'] },
          { name: 'Blast Furnace Melting', sources: ['coal', 'coking_coal', 'grid_electricity', 'natural_gas'] },
          { name: 'Sintering Operations', sources: ['coal', 'grid_electricity', 'natural_gas'] },
        ],
      },
      {
        id: 'eaf',
        name: 'Mini-Mill (EAF)',
        processes: [
          { name: 'Electric Arc Furnace Melting', sources: ['grid_electricity', 'natural_gas'] },
          { name: 'Ladle Refining', sources: ['grid_electricity', 'natural_gas'] },
          { name: 'Scrap Pre-heating', sources: ['natural_gas', 'diesel', 'furnace_oil'] },
        ],
      },
      {
        id: 'foundry',
        name: 'Blast Furnace Foundry',
        processes: [
          { name: 'Cupola Melting', sources: ['coking_coal', 'coal', 'grid_electricity'] },
          { name: 'Casting and Moulding', sources: ['grid_electricity', 'lpg'] },
          { name: 'Heat Treatment', sources: ['natural_gas', 'furnace_oil', 'grid_electricity'] },
        ],
      },
    ],
  },
  {
    id: 'logistics',
    name: 'Logistics & Freight',
    icon: 'truck',
    subsectors: [
      {
        id: 'road',
        name: 'Road Freight Transport',
        processes: [
          { name: 'Heavy-Duty Diesel Trucking', sources: ['diesel', 'truck_distance'] },
          { name: 'Last-Mile Delivery (Petrol Van)', sources: ['petrol', 'van_distance'] },
          { name: 'Refrigeration Unit Chilling', sources: ['diesel', 'refrigerant_r404a'] },
        ],
      },
      {
        id: 'air',
        name: 'Air Cargo Operations',
        processes: [
          { name: 'Cargo Flights', sources: ['jet_fuel'] },
          { name: 'Ground Handling', sources: ['diesel', 'grid_electricity'] },
        ],
      },
      {
        id: 'maritime',
        name: 'Maritime Shipping Fleet',
        processes: [
          { name: 'Ocean Voyage', sources: ['marine_fuel', 'diesel'] },
          { name: 'Port Operations', sources: ['diesel', 'grid_electricity'] },
        ],
      },
      {
        id: 'coldchain',
        name: 'Cold-Chain Distribution',
        processes: [
          { name: 'Refrigerated Storage', sources: ['grid_electricity', 'refrigerant_r404a'] },
          { name: 'Refrigerated Transport', sources: ['diesel', 'refrigerant_r404a'] },
        ],
      },
    ],
  },
  {
    id: 'buildings',
    name: 'Commercial Buildings',
    icon: 'building',
    subsectors: [
      {
        id: 'office',
        name: 'Corporate Offices',
        processes: [
          { name: 'Lighting and Power', sources: ['grid_electricity'] },
          { name: 'HVAC', sources: ['grid_electricity', 'refrigerant_r134a'] },
          { name: 'Backup Generators', sources: ['diesel'] },
        ],
      },
      {
        id: 'retail',
        name: 'Retail Hubs / Malls',
        processes: [
          { name: 'Common Area Power', sources: ['grid_electricity'] },
          { name: 'HVAC and Refrigeration', sources: ['grid_electricity', 'refrigerant_r404a'] },
          { name: 'Backup Generators', sources: ['diesel'] },
        ],
      },
      {
        id: 'datacenter',
        name: 'Data Centers',
        processes: [
          { name: 'IT Load', sources: ['grid_electricity'] },
          { name: 'Cooling', sources: ['grid_electricity', 'refrigerant_r134a'] },
          { name: 'Backup Generators', sources: ['diesel'] },
        ],
      },
    ],
  },
  {
    id: 'power',
    name: 'Power Generation & Utilities',
    icon: 'bolt',
    subsectors: [
      {
        id: 'coalplant',
        name: 'Coal-fired Power Plant',
        processes: [
          { name: 'Boiler Combustion', sources: ['coal'] },
          { name: 'Start-up Fuel', sources: ['furnace_oil', 'diesel'] },
          { name: 'Auxiliary Consumption', sources: ['grid_electricity'] },
        ],
      },
      {
        id: 'gasplant',
        name: 'Gas-fired Power Plant',
        processes: [
          { name: 'Gas Turbine Combustion', sources: ['natural_gas'] },
          { name: 'Auxiliary Consumption', sources: ['grid_electricity'] },
        ],
      },
      {
        id: 'renewable',
        name: 'Solar / Wind Farm',
        processes: [
          { name: 'Auxiliary Consumption', sources: ['grid_electricity'] },
          { name: 'O&M Vehicles', sources: ['diesel', 'petrol'] },
        ],
      },
    ],
  },
  {
    id: 'agri',
    name: 'Agriculture & Food Production',
    icon: 'plant',
    subsectors: [
      {
        id: 'crop',
        name: 'Crop Farming',
        processes: [
          { name: 'Field Machinery', sources: ['diesel'] },
          { name: 'Irrigation Pumping', sources: ['grid_electricity', 'diesel'] },
          { name: 'Fertiliser Application', sources: ['urea'] },
        ],
      },
      {
        id: 'dairy',
        name: 'Dairy Farm',
        processes: [
          { name: 'Milking and Chilling', sources: ['grid_electricity', 'refrigerant_r404a'] },
          { name: 'Feed Processing', sources: ['grid_electricity', 'diesel'] },
        ],
      },
      {
        id: 'foodplant',
        name: 'Food Processing Plant',
        processes: [
          { name: 'Boilers and Cooking', sources: ['natural_gas', 'lpg', 'furnace_oil', 'coal'] },
          { name: 'Cold Storage', sources: ['grid_electricity', 'refrigerant_r404a'] },
          { name: 'Packaging Line', sources: ['grid_electricity'] },
        ],
      },
    ],
  },
  {
    id: 'banking',
    name: 'Banking & Financial Services',
    icon: 'bank',
    subsectors: [
      {
        id: 'branches',
        name: 'Branch Network',
        processes: [
          { name: 'Branch Power', sources: ['grid_electricity'] },
          { name: 'Backup Generators', sources: ['diesel'] },
        ],
      },
      {
        id: 'headoffice',
        name: 'Head Office',
        processes: [
          { name: 'Office Power', sources: ['grid_electricity'] },
          { name: 'HVAC', sources: ['grid_electricity', 'refrigerant_r134a'] },
          { name: 'Business Travel', sources: ['air_travel', 'petrol'] },
        ],
      },
      {
        id: 'bankdc',
        name: 'Data Center',
        processes: [
          { name: 'IT Load', sources: ['grid_electricity'] },
          { name: 'Cooling', sources: ['grid_electricity', 'refrigerant_r134a'] },
        ],
      },
    ],
  },
]

export function findIndustry(id) {
  return INDUSTRIES.find((i) => i.id === id)
}

export function findSubsector(industryId, subsectorId) {
  return findIndustry(industryId)?.subsectors.find((s) => s.id === subsectorId)
}

export function findProcess(industryId, subsectorId, name) {
  return findSubsector(industryId, subsectorId)?.processes.find((p) => p.name === name)
}
