import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function AttendanceView({ onLogout }) {
  const [attendanceRecords, setAttendanceRecords] = useState([])
  const [filter, setFilter] = useState('all') // 'all', 'day', 'month', 'year'
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0])
  const [selectedMonth, setSelectedMonth] = useState(new Date().toISOString().slice(0, 7))
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear().toString())
  const navigate = useNavigate()

  // Initialize mock class attendance data if none exists
  useEffect(() => {
    const existingRecords = JSON.parse(localStorage.getItem('classAttendance') || '[]')
    if (existingRecords.length === 0) {
      // Generate sample class attendance data
      const sampleRecords = generateSampleAttendance()
      localStorage.setItem('classAttendance', JSON.stringify(sampleRecords))
      setAttendanceRecords(sampleRecords.sort((a, b) => new Date(b.date) - new Date(a.date)))
    } else {
      setAttendanceRecords(existingRecords.sort((a, b) => new Date(b.date) - new Date(a.date)))
    }
  }, [])

  const generateSampleAttendance = () => {
    const records = []
    const rooms = ['Room512', 'Room301', 'Room205', 'Room418', 'Room102']
    const classes = ['Class1', 'Class2', 'Class3', 'Class4', 'Class5']
    const statuses = ['present', 'present', 'present', 'present', 'absent'] // 80% present rate
    
    // Generate records for the last 30 days
    for (let i = 0; i < 30; i++) {
      const date = new Date()
      date.setDate(date.getDate() - i)
      
      // Generate 1-3 class records per day
      const numClasses = Math.floor(Math.random() * 3) + 1
      
      for (let j = 0; j < numClasses; j++) {
        const room = rooms[Math.floor(Math.random() * rooms.length)]
        const className = classes[Math.floor(Math.random() * classes.length)]
        const status = statuses[Math.floor(Math.random() * statuses.length)]
        
        // Generate geotag coordinates (mock campus location)
        const latitude = 28.6139 + (Math.random() - 0.5) * 0.01
        const longitude = 77.2090 + (Math.random() - 0.5) * 0.01
        
        records.push({
          id: Date.now() - (i * 86400000) - j,
          date: date.toISOString(),
          timestamp: `${8 + Math.floor(Math.random() * 8)}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}`,
          room: room,
          className: className,
          status: status,
          geotag: {
            latitude: latitude.toFixed(6),
            longitude: longitude.toFixed(6)
          }
        })
      }
    }
    
    return records
  }

  const loadAttendance = () => {
    const records = JSON.parse(localStorage.getItem('classAttendance') || '[]')
    setAttendanceRecords(records.sort((a, b) => new Date(b.date) - new Date(a.date)))
  }

  const getFilteredRecords = () => {
    if (filter === 'all') return attendanceRecords

    const filtered = attendanceRecords.filter(record => {
      const recordDate = new Date(record.date)

      if (filter === 'day') {
        const selected = new Date(selectedDate)
        return (
          recordDate.getDate() === selected.getDate() &&
          recordDate.getMonth() === selected.getMonth() &&
          recordDate.getFullYear() === selected.getFullYear()
        )
      }

      if (filter === 'month') {
        return (
          recordDate.getMonth() === new Date(selectedMonth + '-01').getMonth() &&
          recordDate.getFullYear() === new Date(selectedMonth + '-01').getFullYear()
        )
      }

      if (filter === 'year') {
        return recordDate.getFullYear() === parseInt(selectedYear)
      }

      return true
    })

    return filtered
  }

  const getStats = () => {
    const filtered = getFilteredRecords()
    const totalClasses = filtered.length
    const presentClasses = filtered.filter(r => r.status === 'present').length
    const absentClasses = filtered.filter(r => r.status === 'absent').length
    
    // Get unique rooms and classes
    const uniqueRooms = new Set(filtered.map(r => r.room))
    const uniqueClasses = new Set(filtered.map(r => r.className))
    
    const percentage = totalClasses > 0 ? (presentClasses / totalClasses) * 100 : 0

    return {
      totalClasses,
      presentClasses,
      absentClasses,
      uniqueRooms: uniqueRooms.size,
      uniqueClasses: uniqueClasses.size,
      percentage: Math.min(percentage, 100)
    }
  }

  const stats = getStats()
  const filteredRecords = getFilteredRecords()

  const formatDate = (dateString) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-primary-600">CrowdMuse</h1>
              <p className="text-sm text-gray-600">Class Attendance History</p>
            </div>
            <div className="flex gap-4">
              <button
                onClick={() => navigate('/dashboard')}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-primary-600 transition"
              >
                Dashboard
              </button>
              <button
                onClick={onLogout}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-primary-600 transition"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8">
          <h2 className="text-3xl font-bold text-gray-900 mb-2">Your Class Attendance</h2>
          <p className="text-gray-600">Automatically captured via classroom cameras with geotagging</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-1 md:grid-cols-5 gap-6 mb-8">
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Total Classes</p>
            <p className="text-3xl font-bold text-primary-600">{stats.totalClasses}</p>
            <p className="text-xs text-gray-500 mt-1">attended</p>
          </div>
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Present</p>
            <p className="text-3xl font-bold text-green-600">{stats.presentClasses}</p>
            <p className="text-xs text-gray-500 mt-1">classes</p>
          </div>
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Absent</p>
            <p className="text-3xl font-bold text-red-600">{stats.absentClasses}</p>
            <p className="text-xs text-gray-500 mt-1">classes</p>
          </div>
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Attendance Rate</p>
            <p className="text-3xl font-bold text-blue-600">{stats.percentage.toFixed(1)}%</p>
            <p className="text-xs text-gray-500 mt-1">percentage</p>
          </div>
          <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Rooms</p>
            <p className="text-3xl font-bold text-purple-600">{stats.uniqueRooms}</p>
            <p className="text-xs text-gray-500 mt-1">different</p>
          </div>
        </div>

        {/* Filter Section */}
        <div className="bg-white rounded-xl shadow-md p-6 border border-gray-100 mb-8">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Filter Attendance</h3>
          <div className="flex flex-wrap gap-4 items-end">
            <div className="flex gap-2">
              <button
                onClick={() => setFilter('all')}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  filter === 'all'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                All Time
              </button>
              <button
                onClick={() => setFilter('day')}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  filter === 'day'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                By Day
              </button>
              <button
                onClick={() => setFilter('month')}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  filter === 'month'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                By Month
              </button>
              <button
                onClick={() => setFilter('year')}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  filter === 'year'
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                By Year
              </button>
            </div>

            {filter === 'day' && (
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              />
            )}

            {filter === 'month' && (
              <input
                type="month"
                value={selectedMonth}
                onChange={(e) => setSelectedMonth(e.target.value)}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              />
            )}

            {filter === 'year' && (
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(e.target.value)}
                className="px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent outline-none"
              >
                {Array.from({ length: 5 }, (_, i) => new Date().getFullYear() - i).map(year => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            )}
          </div>
        </div>

        {/* Attendance Records */}
        <div className="bg-white rounded-xl shadow-md border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-200">
            <h3 className="text-lg font-semibold text-gray-900">Class Attendance Records</h3>
          </div>
          {filteredRecords.length === 0 ? (
            <div className="p-12 text-center">
              <svg className="w-16 h-16 mx-auto text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-gray-600 mb-2">No attendance records found</p>
              <p className="text-sm text-gray-500">Your attendance will appear here once captured by classroom cameras</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-200">
              {filteredRecords.map((record) => (
                <div key={record.id} className="px-6 py-4 hover:bg-gray-50 transition">
                  <div className="flex justify-between items-start">
                    <div className="flex items-start gap-4 flex-1">
                      <div className={`w-3 h-3 rounded-full mt-2 ${
                        record.status === 'present' ? 'bg-green-500' : 'bg-red-500'
                      }`} />
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-1">
                          <p className="font-semibold text-lg text-gray-900">{record.room}</p>
                          <span className="px-2 py-1 bg-primary-100 text-primary-700 rounded text-sm font-medium">
                            {record.className}
                          </span>
                          <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                            record.status === 'present'
                              ? 'bg-green-100 text-green-700'
                              : 'bg-red-100 text-red-700'
                          }`}>
                            {record.status === 'present' ? 'Present' : 'Absent'}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-sm text-gray-600">
                          <span className="flex items-center gap-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                            </svg>
                            {formatDate(record.date)}
                          </span>
                          <span className="flex items-center gap-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                            </svg>
                            {record.timestamp}
                          </span>
                          <span className="flex items-center gap-1">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                            </svg>
                            {record.geotag.latitude}, {record.geotag.longitude}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Info Section */}
        <div className="mt-8 bg-blue-50 rounded-xl p-6 border border-blue-200">
          <h3 className="text-lg font-semibold text-blue-900 mb-2">
            How Attendance Works
          </h3>
          <p className="text-blue-700 text-sm mb-2">
            Your attendance is automatically captured by cameras installed at the top of each classroom. 
            The system uses face recognition to identify you and geotags each record with the classroom location.
          </p>
          <ul className="text-blue-700 text-sm space-y-1 list-disc list-inside">
            <li>Attendance is marked automatically when you enter a classroom</li>
            <li>Each record includes the room number, class name, and timestamp</li>
            <li>Geotagging ensures accurate location tracking</li>
            <li>You can filter records by day, month, or year</li>
          </ul>
        </div>
      </main>
    </div>
  )
}

export default AttendanceView
