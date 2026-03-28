import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

function Dashboard({ onLogout }) {
  const navigate = useNavigate()
  const [locations, setLocations] = useState([
    { id: 1, name: 'Canteen', capacity: 200, current: 45, status: 'low' },
    { id: 2, name: 'Library', capacity: 150, current: 120, status: 'high' },
    { id: 3, name: 'Auditorium', capacity: 500, current: 0, status: 'empty' },
    { id: 4, name: 'Study Hall', capacity: 100, current: 65, status: 'medium' },
    { id: 5, name: 'Gym', capacity: 80, current: 30, status: 'low' },
    { id: 6, name: 'Cafeteria', capacity: 120, current: 95, status: 'medium' },
  ])

  // Simulate real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      setLocations(prevLocations =>
        prevLocations.map(location => {
          // Randomly update crowd levels for demo
          const change = Math.floor(Math.random() * 10) - 5
          const newCurrent = Math.max(0, Math.min(location.capacity, location.current + change))
          const percentage = (newCurrent / location.capacity) * 100
          
          let status = 'empty'
          if (percentage > 80) status = 'high'
          else if (percentage > 40) status = 'medium'
          else if (percentage > 0) status = 'low'

          return {
            ...location,
            current: newCurrent,
            status
          }
        })
      )
    }, 5000) // Update every 5 seconds

    return () => clearInterval(interval)
  }, [])

  const getStatusColor = (status) => {
    switch (status) {
      case 'empty':
        return 'bg-gray-100 text-gray-700'
      case 'low':
        return 'bg-green-100 text-green-700'
      case 'medium':
        return 'bg-yellow-100 text-yellow-700'
      case 'high':
        return 'bg-red-100 text-red-700'
      default:
        return 'bg-gray-100 text-gray-700'
    }
  }

  const getStatusText = (status) => {
    switch (status) {
      case 'empty':
        return 'Empty'
      case 'low':
        return 'Low Crowd'
      case 'medium':
        return 'Moderate'
      case 'high':
        return 'Crowded'
      default:
        return 'Unknown'
    }
  }

  const getProgressColor = (percentage) => {
    if (percentage > 80) return 'bg-red-500'
    if (percentage > 40) return 'bg-yellow-500'
    if (percentage > 0) return 'bg-green-500'
    return 'bg-gray-300'
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-2xl font-bold text-primary-600">CrowdMuse</h1>
              <p className="text-sm text-gray-600">Real-time campus crowd information</p>
            </div>
            <div className="flex gap-4">
              <button
                onClick={() => navigate('/attendance/view')}
                className="px-4 py-2 text-sm font-medium text-gray-700 hover:text-primary-600 transition"
              >
                View Attendance
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
          <h2 className="text-3xl font-bold text-gray-900 mb-2">Campus Locations</h2>
          <p className="text-gray-600">Check crowd levels before you go</p>
        </div>

        {/* Location Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {locations.map((location) => {
            const percentage = (location.current / location.capacity) * 100

            return (
              <div
                key={location.id}
                className="bg-white rounded-xl shadow-md hover:shadow-lg transition-shadow duration-200 p-6 border border-gray-100"
              >
                <div className="flex justify-between items-start mb-4">
                  <h3 className="text-xl font-semibold text-gray-900">
                    {location.name}
                  </h3>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium ${getStatusColor(
                      location.status
                    )}`}
                  >
                    {getStatusText(location.status)}
                  </span>
                </div>

                <div className="mb-4">
                  <div className="flex justify-between text-sm text-gray-600 mb-2">
                    <span>Occupancy</span>
                    <span className="font-semibold text-gray-900">
                      {location.current} / {location.capacity}
                    </span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-3 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${getProgressColor(
                        percentage
                      )}`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    {percentage.toFixed(0)}% capacity
                  </p>
                </div>

                <div className="mt-4 pt-4 border-t border-gray-100">
                  <button className="w-full bg-primary-600 hover:bg-primary-700 text-white font-medium py-2 px-4 rounded-lg transition duration-200 text-sm">
                    View Details
                  </button>
                </div>
              </div>
            )
          })}
        </div>

        {/* Quick Actions */}
        <div className="mt-8">
          <div 
            onClick={() => navigate('/attendance/view')}
            className="bg-gradient-to-r from-green-500 to-green-600 rounded-xl shadow-lg p-6 text-white cursor-pointer hover:shadow-xl transition-shadow max-w-md"
          >
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-semibold mb-2">View Class Attendance</h3>
                <p className="text-green-100 text-sm">Check your automatically captured attendance records</p>
              </div>
              <svg className="w-12 h-12 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
          </div>
        </div>

        {/* Info Section */}
        <div className="mt-8 bg-primary-50 rounded-xl p-6 border border-primary-200">
          <h3 className="text-lg font-semibold text-primary-900 mb-2">
            How it works
          </h3>
          <p className="text-primary-700 text-sm">
            CrowdMuse uses real-time data to help you find the best times to visit campus locations. 
            Green indicates low crowd, yellow means moderate, and red means crowded. 
            Perfect for planning your study sessions and meal times!
          </p>
        </div>
      </main>
    </div>
  )
}

export default Dashboard
