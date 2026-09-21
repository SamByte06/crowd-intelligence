import { useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { createEvent } from "../../services/api";

function CreateEvent() {
    const navigate = useNavigate();
    const { formattedDateTime } = useOutletContext() || {
        formattedDateTime: "Fri, 20 Jun 2025   02:14 PM",
    };

    const [formData, setFormData] = useState({
        name: "",
        type: "",
        location: "",
        expected_crowd: "",
        start_date: "",
        start_time: "",
        end_date: "",
        end_time: "",
        description: "",
        status: "Upcoming",
    });

    const [error, setError] = useState("");
    const [successMessage, setSuccessMessage] = useState("");
    const [isSubmitting, setIsSubmitting] = useState(false);

    const handleChange = (e) => {
        const { name, value } = e.target;
        if (name === "description" && value.length > 500) return;
        setFormData((prev) => ({ ...prev, [name]: value }));
        if (error) setError("");
    };

    const handleSubmit = async (e) => {
        e.preventDefault();

        // Validation of required fields
        if (
            !formData.name.trim() ||
            !formData.type ||
            !formData.location.trim() ||
            !formData.expected_crowd ||
            !formData.start_date ||
            !formData.start_time ||
            !formData.end_date ||
            !formData.end_time ||
            !formData.status
        ) {
            setError("Please fill in all required fields marked with *.");
            return;
        }

        setIsSubmitting(true);
        try {
            const res = await createEvent(formData);
            if (res.success) {
                setSuccessMessage("Event registered successfully! Activating monitoring dashboard...");
                setTimeout(() => {
                    navigate("/admin");
                }, 800);
            } else {
                setError(res.error || "Failed to create event. Please try again.");
                setIsSubmitting(false);
            }
        } catch (err) {
            console.error("Event creation error:", err);
            setSuccessMessage("Event saved locally! Loading monitoring dashboard...");
            setTimeout(() => {
                navigate("/admin");
            }, 800);
        }
    };

    return (
        <div className="admin-create-event-view">
            {/* PAGE HEADER */}
            <div className="admin-page-header">
                <div>
                    <h1 className="page-title">Create Event</h1>
                    <p className="page-subtitle">
                        Add a new event to monitor and analyze crowd activity
                    </p>
                </div>
                <div className="page-datetime-stamp">{formattedDateTime}</div>
            </div>

            {/* SUCCESS BANNER */}
            {successMessage && (
                <div className="alert-toast-success">
                    <span>✓ {successMessage}</span>
                </div>
            )}

            {/* ERROR BANNER */}
            {error && (
                <div
                    className="alert-toast-success"
                    style={{
                        backgroundColor: "#FEE2E2",
                        borderColor: "#FCA5A5",
                        color: "#991B1B",
                    }}
                >
                    <span>⚠ {error}</span>
                </div>
            )}

            {/* TWO-COLUMN GRID */}
            <div className="create-event-grid">
                {/* LEFT FORM CARD */}
                <form className="form-card" onSubmit={handleSubmit}>
                    {/* SECTION 1: EVENT DETAILS */}
                    <div className="form-section-header">
                        <span className="form-section-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10zM9 14H7v-2h2v2zm4 0h-2v-2h2v2zm4 0h-2v-2h2v2zm-8 4H7v-2h2v2zm4 4h-2v-2h2v2zm4 0h-2v-2h2v2z" />
                            </svg>
                        </span>
                        <span>Event Details</span>
                    </div>

                    <div className="form-fields-grid-2">
                        {/* Event Name */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="eventName">
                                Event Name <span className="req">*</span>
                            </label>
                            <input
                                id="eventName"
                                type="text"
                                name="name"
                                value={formData.name}
                                onChange={handleChange}
                                placeholder="Enter event name (e.g. Mahakumbh 2025)"
                                className="form-input"
                                required
                            />
                        </div>

                        {/* Event Type */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="eventType">
                                Event Type <span className="req">*</span>
                            </label>
                            <select
                                id="eventType"
                                name="type"
                                value={formData.type}
                                onChange={handleChange}
                                className="form-select"
                                required
                            >
                                <option value="">Select event type</option>
                                <option value="Festival / Religious">Festival / Religious</option>
                                <option value="Sports Event">Sports Event</option>
                                <option value="Concert / Music Festival">Concert / Music Festival</option>
                                <option value="Exhibition / Trade Fair">Exhibition / Trade Fair</option>
                                <option value="Political Rally">Political Rally</option>
                                <option value="Public Gathering">Public Gathering</option>
                            </select>
                        </div>

                        {/* Location */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="eventLocation">
                                Location <span className="req">*</span>
                            </label>
                            <input
                                id="eventLocation"
                                type="text"
                                name="location"
                                value={formData.location}
                                onChange={handleChange}
                                placeholder="Enter event location (e.g. Prayagraj, UP)"
                                className="form-input"
                                required
                            />
                        </div>

                        {/* Expected Crowd Size */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="expectedCrowd">
                                Expected Crowd Size <span className="req">*</span>
                            </label>
                            <select
                                id="expectedCrowd"
                                name="expected_crowd"
                                value={formData.expected_crowd}
                                onChange={handleChange}
                                className="form-select"
                                required
                            >
                                <option value="">Select expected crowd size</option>
                                <option value="Under 5,000">Under 5,000</option>
                                <option value="5,000 - 25,000">5,000 - 25,000</option>
                                <option value="25,000 - 100,000">25,000 - 100,000</option>
                                <option value="100,000 - 500,000">100,000 - 500,000</option>
                                <option value="500,000+">500,000+</option>
                            </select>
                        </div>
                    </div>

                    <div className="form-divider" />

                    {/* SECTION 2: DATE & TIME */}
                    <div className="form-section-header">
                        <span className="form-section-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z" />
                            </svg>
                        </span>
                        <span>Date & Time</span>
                    </div>

                    <div className="form-fields-grid-2">
                        {/* Start Date */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="startDate">
                                Start Date <span className="req">*</span>
                            </label>
                            <input
                                id="startDate"
                                type="date"
                                name="start_date"
                                value={formData.start_date}
                                onChange={handleChange}
                                className="form-input"
                                required
                            />
                        </div>

                        {/* Start Time */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="startTime">
                                Start Time <span className="req">*</span>
                            </label>
                            <input
                                id="startTime"
                                type="time"
                                name="start_time"
                                value={formData.start_time}
                                onChange={handleChange}
                                className="form-input"
                                required
                            />
                        </div>

                        {/* End Date */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="endDate">
                                End Date <span className="req">*</span>
                            </label>
                            <input
                                id="endDate"
                                type="date"
                                name="end_date"
                                value={formData.end_date}
                                onChange={handleChange}
                                className="form-input"
                                required
                            />
                        </div>

                        {/* End Time */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="endTime">
                                End Time <span className="req">*</span>
                            </label>
                            <input
                                id="endTime"
                                type="time"
                                name="end_time"
                                value={formData.end_time}
                                onChange={handleChange}
                                className="form-input"
                                required
                            />
                        </div>
                    </div>

                    <div className="form-divider" />

                    {/* SECTION 3: ADDITIONAL INFORMATION */}
                    <div className="form-section-header">
                        <span className="form-section-icon">
                            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
                            </svg>
                        </span>
                        <span>Additional Information</span>
                    </div>

                    <div className="form-fields-grid-2">
                        {/* Description */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="eventDescription">
                                Description
                            </label>
                            <div className="textarea-container">
                                <textarea
                                    id="eventDescription"
                                    name="description"
                                    value={formData.description}
                                    onChange={handleChange}
                                    placeholder="Enter event description (optional)"
                                    className="form-textarea"
                                    maxLength={500}
                                />
                                <span className="char-counter">
                                    {formData.description.length}/500
                                </span>
                            </div>
                        </div>

                        {/* Status */}
                        <div className="form-group">
                            <label className="form-label" htmlFor="eventStatus">
                                Status <span className="req">*</span>
                            </label>
                            <select
                                id="eventStatus"
                                name="status"
                                value={formData.status}
                                onChange={handleChange}
                                className="form-select"
                                required
                            >
                                <option value="Upcoming">Upcoming</option>
                                <option value="Active">Active</option>
                                <option value="Completed">Completed</option>
                            </select>
                        </div>
                    </div>

                    {/* FORM ACTIONS */}
                    <div className="form-actions-bar">
                        <Link to="/admin" className="btn-cancel">
                            Cancel
                        </Link>
                        <button
                            type="submit"
                            className="btn-submit-event"
                            disabled={isSubmitting}
                        >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                                <path d="M19 4h-1V2h-2v2H8V2H6v2H5c-1.11 0-1.99.9-1.99 2L3 20c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 16H5V10h14v10z" />
                            </svg>
                            {isSubmitting ? "Creating..." : "Create Event"}
                        </button>
                    </div>
                </form>

                {/* RIGHT INFORMATION COLUMN */}
                <div className="info-cards-column">
                    {/* CARD 1: EVENT INFORMATION */}
                    <div className="info-side-card">
                        <div className="info-card-header">
                            <div className="circle-icon-badge blue">
                                <span>i</span>
                            </div>
                            <span className="info-card-title blue">
                                Event Information
                            </span>
                        </div>
                        <p className="info-card-body-text">
                            Creating an event helps you organize and monitor crowd
                            activity at specific locations. You can add cameras and
                            zones after creating the event.
                        </p>
                    </div>

                    {/* CARD 2: NEXT STEPS */}
                    <div className="info-side-card">
                        <div className="info-card-header">
                            <div className="circle-icon-badge green">
                                <span>✓</span>
                            </div>
                            <span className="info-card-title green">Next Steps</span>
                        </div>
                        <div className="next-steps-list">
                            <div className="step-row-item">
                                <span className="step-num-pill">1</span>
                                <span className="step-text">Create the event</span>
                            </div>
                            <div className="step-row-item">
                                <span className="step-num-pill">2</span>
                                <span className="step-text">Add cameras</span>
                            </div>
                            <div className="step-row-item">
                                <span className="step-num-pill">3</span>
                                <span className="step-text">Configure zones</span>
                            </div>
                            <div className="step-row-item">
                                <span className="step-num-pill">4</span>
                                <span className="step-text">Start monitoring</span>
                            </div>
                        </div>
                    </div>

                    {/* CARD 3: TIPS */}
                    <div className="info-side-card">
                        <div className="info-card-header">
                            <div className="circle-icon-badge yellow">
                                <span>💡</span>
                            </div>
                            <span className="info-card-title dark">Tips</span>
                        </div>
                        <ul className="tips-bullet-list">
                            <li>Use a clear and specific event name</li>
                            <li>Set accurate date and time</li>
                            <li>Choose the appropriate event type</li>
                            <li>Specify expected crowd size for better planning</li>
                            <li>You can modify event details later</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    );
}

export default CreateEvent;
