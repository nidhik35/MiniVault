import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import "./Activity.css";

function Activity() {
    const [activities, setActivities] = useState([]);

    const loadActivities = useCallback(async () => {
        try {
            const res = await axios.get("http://127.0.0.1:5000/activity");
            setActivities(res.data);
        } catch (err) {
            console.error(err);
        }
    }, []);

    useEffect(() => {
    void Promise.resolve().then(loadActivities);

    const interval = setInterval(() => {
        loadActivities();
    }, 5000);

    return () => clearInterval(interval);
}, [loadActivities]);

    return (
        <div className="activity-page">
            <h2>📝 Recent Activity</h2>

            <table className="activity-table">
                <thead>
                    <tr>
                        <th>Action</th>
                        <th>File</th>
                        <th>Time</th>
                    </tr>
                </thead>

                <tbody>
                    {activities.map((item, index) => (
                        <tr key={index}>
                            <td>
  <span
    className={
      item.action === "Backup"
        ? "badge backup"
        : item.action === "Restore"
        ? "badge restore"
          : item.action.endsWith("Failed")
            ? "badge failure"
            : "badge delete"
    }
  >
    {item.action}
  </span>
</td>
                            <td>{item.file}</td>
                            <td>{item.time}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default Activity;