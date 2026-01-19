# CrowdMuse - Campus Crowd Management App

A modern web application for college students to manage attendance and check crowd levels in various campus locations like canteen, auditorium, library, and more.

## Features

- 🔐 **User Authentication** - Simple login interface for students
- 📊 **Real-time Crowd Information** - Live updates on occupancy levels
- 🎯 **Multiple Locations** - Track crowd in canteen, library, auditorium, study halls, gym, and cafeteria
- 👤 **Automatic Class Attendance** - Attendance captured automatically by classroom cameras
- 📍 **Geotagged Records** - Each attendance record includes location coordinates
- 🏫 **Class-Based Tracking** - View attendance by room number and class name (e.g., "Room512 Class1")
- 📅 **Attendance Management** - View attendance history filtered by day, month, or year
- 📈 **Attendance Statistics** - Track attendance percentage, present/absent counts, and room statistics
- 🎨 **Modern UI** - Beautiful, student-friendly interface with color-coded status indicators
- 📱 **Responsive Design** - Works on desktop, tablet, and mobile devices

## Getting Started

### Prerequisites

- Node.js (v16 or higher)
- npm or yarn

### Installation

1. Install dependencies:
```bash
npm install
```

2. Start the development server:
```bash
npm run dev
```

3. Open your browser and navigate to `http://localhost:5173`

### Building for Production

```bash
npm run build
```

The built files will be in the `dist` directory.

## Usage

1. **Login**: Enter any email and password (demo mode - all credentials work)
2. **Dashboard**: View real-time crowd information for all campus locations
3. **View Class Attendance**: 
   - Access your attendance history from the dashboard
   - See automatically captured records from classroom cameras
   - Each record shows: Room number (e.g., Room512), Class name (e.g., Class1), Status (Present/Absent), Date, Time, and Geotag coordinates
   - Filter by day, month, year, or view all records
   - See statistics including total classes, present/absent counts, attendance rate, and unique rooms
5. **Status Indicators**:
   - 🟢 **Green (Low Crowd)**: 0-40% capacity
   - 🟡 **Yellow (Moderate)**: 40-80% capacity
   - 🔴 **Red (Crowded)**: 80-100% capacity
   - ⚪ **Gray (Empty)**: 0% capacity

## Tech Stack

- **React** - UI framework
- **React Router** - Navigation
- **Tailwind CSS** - Styling
- **Vite** - Build tool

## Project Structure

```
crowdmuse/
├── src/
│   ├── components/
│   │   ├── Login.jsx         # Login page component
│   │   ├── Dashboard.jsx     # Main dashboard with crowd information
│   │   └── AttendanceView.jsx # Class attendance history and statistics
│   ├── App.jsx               # Main app component with routing
│   ├── main.jsx              # Entry point
│   └── index.css             # Global styles
├── index.html
├── package.json
└── README.md
```

## Attendance Features

- **Automatic Capture**: Attendance is automatically captured by cameras installed at the top of each classroom
- **Face Recognition**: Classroom cameras use face recognition to identify students
- **Geotagging**: Each attendance record includes geotag coordinates for accurate location tracking
- **Class-Based Records**: Records show room number (e.g., Room512) and class name (e.g., Class1)
- **Status Tracking**: See present/absent status for each class
- **Local Storage**: Attendance records are stored locally in the browser (ready to migrate to backend API)
- **Filtering Options**: View attendance by specific day, month, year, or all time
- **Statistics Dashboard**: See total classes, present/absent counts, attendance rate, and unique rooms visited

## Future Enhancements

- Connect to real backend API for authentication and attendance storage
- Integrate with actual classroom camera systems and face recognition API
- Real-time attendance updates as students enter classrooms
- Implement attendance reports and export functionality
- Add notifications for low attendance warnings
- Implement location-specific details and history
- Add notifications for crowd level changes
- User preferences and favorite locations
- Class schedule integration

## License

MIT
